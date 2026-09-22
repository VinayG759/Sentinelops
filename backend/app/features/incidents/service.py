"""Incident lifecycle. Every state change is written together with its event."""

import asyncio
import time
from uuid import UUID

from app.core import events, prometheus
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
    start = end - minutes * 60
    step = max(10, (minutes * 60) // 120)
    window = "1m"
    error_ratio, request_rate, p95 = await asyncio.gather(
        prometheus.query_range(
            f"sum(rate({prefix}_errors_total[{window}])) / "
            f"sum(rate({prefix}_requests_total[{window}]))",
            start, end, step,
        ),
        prometheus.query_range(f"sum(rate({prefix}_requests_total[{window}]))", start, end, step),
        prometheus.query_range(
            f"histogram_quantile(0.95, sum(rate({prefix}_request_duration_ms_bucket[{window}]))"
            " by (le))",
            start, end, step,
        ),
    )
    return {
        "service": incident["service"],
        "opened_at": incident["opened_at"],
        "resolved_at": incident["resolved_at"],
        "series": {
            "error_ratio": error_ratio,
            "requests_per_second": request_rate,
            "p95_latency_ms": p95,
        },
    }


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
