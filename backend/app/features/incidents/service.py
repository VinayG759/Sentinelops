"""Incident lifecycle. Every state change is written together with its event."""

import time
from uuid import UUID

from app.core import events, service_metrics
from app.core.db import get_pool

_COLUMNS = "id, service, signal, severity, status, title, fs_ticket_id, opened_at, resolved_at"


async def open_incident(
    service: str, signal: str, severity: str, title: str, evidence: dict
) -> dict | None:
    """Open an incident unless one is already open for (service, signal). Returns it, or None."""
    fingerprint = f"{service}:{signal}"
    async with get_pool().connection() as conn:
        incident = await (
            await conn.execute(
                f"""insert into public.incidents (service, signal, severity, title, fingerprint)
                    values (%s, %s, %s, %s, %s)
                    on conflict (fingerprint) where status <> 'resolved' do nothing
                    returning {_COLUMNS}""",
                (service, signal, severity, title, fingerprint),
            )
        ).fetchone()
        if incident is None:
            return None  # already open — dedup by fingerprint
        event = await events.insert(
            conn,
            "incident.opened",
            "system",
            {"service": service, "signal": signal, "severity": severity, "title": title,
             **evidence},
            incident["id"],
        )
    events.dispatch(event)
    return incident


async def list_incidents(status: str | None) -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            f"select {_COLUMNS} from public.incidents "
            "where %(status)s::text is null or status = %(status)s "
            "order by opened_at desc limit 200",
            {"status": status},
        )
        return await cur.fetchall()


async def get_incident(incident_id: UUID) -> dict | None:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            f"select {_COLUMNS} from public.incidents where id = %s", (incident_id,)
        )
        return await cur.fetchone()


async def incident_events(incident_id: UUID) -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select id, incident_id, type, actor, payload, created_at, hash "
            "from public.events where incident_id = %s order by id",
            (incident_id,),
        )
        return await cur.fetchall()


async def recent_events(limit: int) -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select id, incident_id, type, actor, payload, created_at, hash "
            "from public.events order by id desc limit %s",
            (limit,),
        )
        return await cur.fetchall()


async def incident_metrics(incident: dict, minutes: int) -> dict:
    """Time series for the incident's service: one shared time axis, three lines."""
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select metric_prefix from public.services where name = %s", (incident["service"],)
        )
        row = await cur.fetchone()
    prefix = row["metric_prefix"] if row else None
    if not prefix:
        return {"series": {}, "opened_at": incident["opened_at"]}

    end = time.time()
    return {
        "service": incident["service"],
        "opened_at": incident["opened_at"],
        "resolved_at": incident["resolved_at"],
        "series": await service_metrics.series(
            prefix, end - minutes * 60, end, service_metrics.step_for(minutes)
        ),
    }


async def incident_stats(minutes: int) -> dict:
    """Outcome numbers for incidents opened in the window. Every figure comes from the
    incidents table and the event log; the resolving actor distinguishes a verified
    automatic close ('system') from a human one ('user:<id>')."""
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            """
            with inc as (
                select id, opened_at, resolved_at from public.incidents
                where opened_at >= now() - make_interval(mins => %(minutes)s)
            ),
            root_cause as (
                select e.incident_id, min(e.created_at) as at
                from public.events e join inc on inc.id = e.incident_id
                where e.type = 'investigation.completed'
                group by e.incident_id
            ),
            last_resolution as (
                select distinct on (e.incident_id) e.incident_id, e.actor
                from public.events e join inc on inc.id = e.incident_id
                where e.type = 'incident.resolved'
                order by e.incident_id, e.id desc
            )
            select
                (select count(*) from inc) as opened,
                (select count(*) from inc where resolved_at is not null) as resolved,
                (select count(*) from last_resolution lr
                   join inc on inc.id = lr.incident_id
                  where lr.actor = 'system' and inc.resolved_at is not null)
                    as closed_by_verified_fix,
                (select percentile_cont(0.5) within group
                        (order by extract(epoch from rc.at - inc.opened_at))
                   from root_cause rc join inc on inc.id = rc.incident_id)
                    as median_seconds_to_root_cause,
                (select percentile_cont(0.5) within group
                        (order by extract(epoch from resolved_at - opened_at))
                   from inc where resolved_at is not null)
                    as median_seconds_to_resolve,
                (select count(*) from public.events
                  where type = 'rollback.succeeded'
                    and created_at >= now() - make_interval(mins => %(minutes)s))
                    as rollbacks
            """,
            {"minutes": minutes},
        )
        row = await cur.fetchone()
    return {"minutes": minutes, **row}


# Allowed transitions: to-status -> the statuses it may be reached from.
# "triggered" is reachable again after a failed fix is rolled back.
_TRANSITIONS = {
    "acknowledged": {"triggered"},
    "resolved": {"triggered", "acknowledged"},
    "triggered": {"acknowledged", "resolved"},
}


async def transition(incident_id: UUID, to: str, actor: str) -> dict | None:
    """Move an incident to `to` if allowed from its current status. None if not allowed."""
    allowed_from = list(_TRANSITIONS[to])
    async with get_pool().connection() as conn:
        incident = await (
            await conn.execute(
                f"""update public.incidents
                    set status = %s,
                        resolved_at = case when %s = 'resolved' then now() else resolved_at end
                    where id = %s and status = any(%s)
                    returning {_COLUMNS}""",
                (to, to, incident_id, allowed_from),
            )
        ).fetchone()
        if incident is None:
            return None
        event = await events.insert(conn, f"incident.{to}", actor, {}, incident_id)
    events.dispatch(event)
    return incident
