"""Guarantees enforced by the database itself. Runs against the dev Supabase project
inside a transaction that is always rolled back, so nothing is left behind.

    uv run pytest -m db
"""

from itertools import pairwise

import psycopg
import pytest

from app.core.config import get_settings

pytestmark = pytest.mark.db


@pytest.fixture
def cur():
    url = get_settings().supabase_db_url
    if not url:
        pytest.skip("SUPABASE_DB_URL not set")
    with psycopg.connect(url, prepare_threshold=None) as conn:
        try:
            yield conn.cursor()
        finally:
            conn.rollback()


def _add_events(cur, n: int) -> None:
    for i in range(n):
        cur.execute(
            "insert into events (type, actor, payload) values ('test.event', 'system', %s)",
            (psycopg.types.json.Jsonb({"i": i}),),
        )


def _verify(cur) -> tuple:
    return cur.execute("select * from verify_event_chain()").fetchone()


def test_chain_links_each_event_to_the_previous(cur):
    before = cur.execute("select count(*) from events").fetchone()[0]
    _add_events(cur, 3)
    rows = cur.execute("select prev_hash, hash from events order by id").fetchall()
    for (_, previous_hash), (prev_hash, _) in pairwise(rows):
        assert prev_hash == previous_hash
    assert _verify(cur) == (True, before + 3, None)


@pytest.mark.parametrize("sql", ["update events set actor = 'x'", "delete from events"])
def test_events_cannot_be_changed(cur, sql):
    _add_events(cur, 1)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        cur.execute(sql)


def test_tampering_is_detected_and_located(cur):
    _add_events(cur, 3)
    target = cur.execute("select id from events order by id desc limit 1 offset 1").fetchone()[0]
    cur.execute("alter table events disable trigger events_no_update")  # simulate a DB owner
    cur.execute("update events set payload = '{\"i\": 999}' where id = %s", (target,))
    valid, _, broken = _verify(cur)
    assert valid is False
    assert broken == target


def _proposal(cur) -> str:
    incident_id = cur.execute(
        "insert into incidents (service, signal, severity, title, fingerprint) "
        "values ('order-service', 'error_rate', 'sev1', 't', 'order-service:race') returning id"
    ).fetchone()[0]
    return cur.execute(
        "insert into proposals (incident_id, action, params, rationale, risk) "
        "values (%s, 'restart_service', '{}', 'r', 'low') returning id",
        (incident_id,),
    ).fetchone()[0]


def test_a_proposal_can_only_be_approved_once(cur):
    """Two approvers clicking at the same moment: the second update matches no rows."""
    proposal_id = _proposal(cur)
    claim = (
        "update proposals set status = 'approved' "
        "where id = %s and status = 'pending' and expires_at > now() returning id"
    )
    assert cur.execute(claim, (proposal_id,)).fetchone() is not None
    assert cur.execute(claim, (proposal_id,)).fetchone() is None


def test_an_expired_proposal_cannot_be_approved(cur):
    proposal_id = _proposal(cur)
    cur.execute("update proposals set expires_at = now() - interval '1 minute' where id = %s",
                (proposal_id,))
    claim = (
        "update proposals set status = 'approved' "
        "where id = %s and status = 'pending' and expires_at > now() returning id"
    )
    assert cur.execute(claim, (proposal_id,)).fetchone() is None


def test_a_proposal_can_only_execute_once(cur):
    """The unique constraint on executions.proposal_id is the last line of defence."""
    proposal_id = _proposal(cur)
    cur.execute("insert into executions (proposal_id) values (%s)", (proposal_id,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        cur.execute("insert into executions (proposal_id) values (%s)", (proposal_id,))


def test_only_one_open_incident_per_fingerprint(cur):
    insert = (
        "insert into incidents (service, signal, severity, title, fingerprint) "
        "values ('order-service', 'error_rate', 'sev1', 't', 'order-service:test') "
        "on conflict (fingerprint) where status <> 'resolved' do nothing returning id"
    )
    assert cur.execute(insert).fetchone() is not None
    assert cur.execute(insert).fetchone() is None
