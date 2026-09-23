"""Reading and verifying the audit chain.

Every event is sealed by a database trigger: its hash covers the previous event's
hash plus its own contents, so changing any event breaks every event after it.
`verify_event_chain()` recomputes the whole chain in the database — this module
only reads. Nothing here can write to `public.events`.
"""

import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

from app.core.db import get_pool

MAX_PAGE = 500
DEFAULT_PAGE = 200

_COLUMNS = "id, incident_id, type, actor, payload, created_at, prev_hash, hash"


async def verify_chain() -> dict:
    """Walk every event and recompute its hash. O(n) in the database, not over the wire."""
    started = time.perf_counter()
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select valid, checked, first_broken_id from public.verify_event_chain()"
        )
        row = await cur.fetchone()
    return {
        **row,
        "verified_at": datetime.now(UTC),
        "took_ms": round((time.perf_counter() - started) * 1000),
    }


async def list_events(
    limit: int = DEFAULT_PAGE,
    before_id: int | None = None,
    incident_id: UUID | None = None,
) -> list[dict]:
    """Newest events first. `before_id` pages backwards through the chain."""
    where, params = [], []
    if before_id is not None:
        where.append("id < %s")
        params.append(before_id)
    if incident_id is not None:
        where.append("incident_id = %s")
        params.append(incident_id)
    clause = f"where {' and '.join(where)}" if where else ""
    params.append(min(limit, MAX_PAGE))

    async with get_pool().connection() as conn:
        cur = await conn.execute(
            f"select {_COLUMNS} from public.events {clause} order by id desc limit %s", params
        )
        return await cur.fetchall()


async def export_lines() -> AsyncIterator[str]:
    """The whole chain as JSON lines, oldest first, streamed so memory stays flat."""
    async with get_pool().connection() as conn:
        async with conn.cursor(name="audit_export") as cur:  # server-side cursor
            await cur.execute(f"select {_COLUMNS} from public.events order by id")
            async for row in cur:
                yield json.dumps(row, default=str) + "\n"
