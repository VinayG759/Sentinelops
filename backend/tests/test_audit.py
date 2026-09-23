"""The audit read layer.

The chain's integrity is guaranteed by the database and proved in
`test_database_guarantees.py`. These tests cover the layer above it: that we ask the
database the right question, never ask for more rows than we allow, and stream the
export instead of building it in memory.
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.features.audit import service


class FakeCursor:
    def __init__(self, rows, calls=None):
        self.rows, self.calls = rows, calls

    async def fetchone(self):
        return self.rows[0]

    async def fetchall(self):
        return self.rows

    async def execute(self, sql, params=None):
        if self.calls is not None:
            self.calls.append((sql, params))

    def __aiter__(self):
        async def gen():
            for row in self.rows:
                yield row

        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, rows, calls):
        self.rows, self.calls = rows, calls

    async def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeCursor(self.rows)

    def cursor(self, name=None):
        self.calls.append(("cursor", name))
        return FakeCursor(self.rows, self.calls)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, rows, calls):
        self.rows, self.calls = rows, calls

    def connection(self):
        return FakeConnection(self.rows, self.calls)


@pytest.fixture
def db(monkeypatch):
    """Returns (set_rows, calls). `calls` records every statement the service issued."""
    state = {"rows": []}
    calls: list = []
    monkeypatch.setattr(service, "get_pool", lambda: FakePool(state["rows"], calls))

    def set_rows(rows):
        state["rows"] = rows

    return set_rows, calls


def event(id: int, **overrides) -> dict:
    return {
        "id": id,
        "incident_id": UUID("612ff4b5-9d66-4cf8-b23e-5abf76891990"),
        "type": "incident.opened",
        "actor": "system",
        "payload": {"title": "payment-service failing"},
        "created_at": datetime(2026, 9, 23, 12, 0, tzinfo=UTC),
        "prev_hash": "genesis",
        "hash": "abc123",
        **overrides,
    }


# ── verify ───────────────────────────────────────────────────────────────────


async def test_verify_reports_an_intact_chain(db):
    set_rows, _ = db
    set_rows([{"valid": True, "checked": 511, "first_broken_id": None}])

    status = await service.verify_chain()

    assert status["valid"] is True
    assert status["checked"] == 511
    assert status["first_broken_id"] is None


async def test_verify_names_the_first_broken_event(db):
    set_rows, _ = db
    set_rows([{"valid": False, "checked": 42, "first_broken_id": 41}])

    status = await service.verify_chain()

    assert status["valid"] is False
    # The badge says "broken at #41", so the id has to survive the round trip.
    assert status["first_broken_id"] == 41


async def test_verify_records_when_and_how_long(db):
    """The badge claims a moment in time; it must come from the check, not the page load."""
    set_rows, _ = db
    set_rows([{"valid": True, "checked": 1, "first_broken_id": None}])

    status = await service.verify_chain()

    assert isinstance(status["verified_at"], datetime)
    assert status["verified_at"].tzinfo is not None
    assert isinstance(status["took_ms"], int)
    assert status["took_ms"] >= 0


# ── listing ──────────────────────────────────────────────────────────────────


async def test_events_come_back_newest_first(db):
    set_rows, calls = db
    set_rows([event(3), event(2), event(1)])

    rows = await service.list_events()

    assert [r["id"] for r in rows] == [3, 2, 1]
    assert "order by id desc" in calls[0][0]


async def test_listing_without_filters_has_no_where_clause(db):
    set_rows, calls = db
    set_rows([])

    await service.list_events()

    sql, params = calls[0]
    assert "where" not in sql
    assert params == [service.DEFAULT_PAGE]


async def test_paging_backwards_asks_for_older_events(db):
    set_rows, calls = db
    set_rows([])

    await service.list_events(limit=50, before_id=300)

    sql, params = calls[0]
    assert "id < %s" in sql
    assert params == [300, 50]


async def test_listing_can_be_scoped_to_one_incident(db):
    set_rows, calls = db
    set_rows([])
    incident = uuid4()

    await service.list_events(incident_id=incident)

    sql, params = calls[0]
    assert "incident_id = %s" in sql
    assert params == [incident, service.DEFAULT_PAGE]


async def test_both_filters_combine(db):
    set_rows, calls = db
    set_rows([])
    incident = uuid4()

    await service.list_events(limit=10, before_id=99, incident_id=incident)

    sql, params = calls[0]
    assert "id < %s and incident_id = %s" in sql
    assert params == [99, incident, 10]


async def test_an_oversized_page_is_capped(db):
    """A caller asking for a million rows gets MAX_PAGE, not a million rows."""
    set_rows, calls = db
    set_rows([])

    await service.list_events(limit=1_000_000)

    assert calls[0][1] == [service.MAX_PAGE]


# ── export ───────────────────────────────────────────────────────────────────


async def test_export_is_one_json_object_per_line(db):
    set_rows, _ = db
    set_rows([event(1), event(2)])

    lines = [line async for line in service.export_lines()]

    assert len(lines) == 2
    assert all(line.endswith("\n") for line in lines)
    first = json.loads(lines[0])
    assert first["id"] == 1
    assert first["hash"] == "abc123"


async def test_export_serialises_uuids_and_timestamps(db):
    """json.dumps cannot handle UUID or datetime on its own — the export must not crash."""
    set_rows, _ = db
    set_rows([event(1)])

    line = await anext(service.export_lines())

    parsed = json.loads(line)
    assert parsed["incident_id"] == "612ff4b5-9d66-4cf8-b23e-5abf76891990"
    assert parsed["created_at"].startswith("2026-09-23")


async def test_export_reads_oldest_first_through_a_server_side_cursor(db):
    """Oldest first so the file can be replayed as a chain; named cursor so it streams."""
    set_rows, calls = db
    set_rows([event(1)])

    [line async for line in service.export_lines()]

    assert ("cursor", "audit_export") in calls
    statements = [sql for sql, _ in calls if sql != "cursor"]
    assert any("order by id" in sql and "desc" not in sql for sql in statements)
