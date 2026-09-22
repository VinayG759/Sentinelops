"""The event log: the only way features talk to each other.

A feature *emits* an event ("incident.opened"); other features *subscribe*
with `@on("incident.opened")`. Every event is stored in the append-only,
hash-chained `events` table (the chain is computed by a database trigger),
so this log is also the audit trail and the incident timeline.

Isolation guarantee: each subscriber runs in its own task. If one raises,
a `handler.failed` event is recorded and nothing else is affected.
"""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from app.core.db import get_pool

log = logging.getLogger(__name__)

Event = dict[str, Any]
Handler = Callable[[Event], Awaitable[None]]

_subscribers: dict[str, list[Handler]] = defaultdict(list)
_running: set[asyncio.Task] = set()  # keep references so tasks aren't garbage-collected


def on(event_type: str) -> Callable[[Handler], Handler]:
    """Decorator: run `handler(event)` whenever an event of this type is emitted."""

    def register(handler: Handler) -> Handler:
        _subscribers[event_type].append(handler)
        return handler

    return register


async def insert(
    conn: AsyncConnection,
    type: str,
    actor: str,
    payload: dict | None = None,
    incident_id: UUID | str | None = None,
) -> Event:
    """Write an event inside the caller's transaction. Call `dispatch()` after commit."""
    cur = await conn.execute(
        "insert into public.events (incident_id, type, actor, payload) values (%s, %s, %s, %s) "
        "returning id, incident_id, type, actor, payload, created_at, hash",
        (incident_id, type, actor, Jsonb(payload or {})),
    )
    return await cur.fetchone()


async def emit(
    type: str, actor: str, payload: dict | None = None, incident_id: UUID | str | None = None
) -> Event:
    """Write an event in its own transaction, then notify subscribers."""
    async with get_pool().connection() as conn:
        event = await insert(conn, type, actor, payload, incident_id)
    dispatch(event)
    return event


def dispatch(event: Event) -> None:
    """Start each subscriber for this event in its own isolated task."""
    for handler in _subscribers.get(event["type"], []):
        task = asyncio.create_task(_run_isolated(handler, event))
        _running.add(task)
        task.add_done_callback(_running.discard)


async def _run_isolated(handler: Handler, event: Event) -> None:
    try:
        await handler(event)
    except Exception as exc:
        name = f"{handler.__module__}.{handler.__qualname__}"
        log.exception("subscriber failed", extra={"handler": name, "event_id": event["id"]})
        if event["type"] == "handler.failed":
            return  # never loop on failure reports
        try:
            await emit(
                "handler.failed",
                "system",
                {"handler": name, "event_id": event["id"], "error": f"{type(exc).__name__}: {exc}"},
                event.get("incident_id"),
            )
        except Exception:
            log.exception("could not record handler failure")
