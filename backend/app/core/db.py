"""Connection pool to SentinelOps' own database (Supabase Postgres).

Never points at the monitored in-cluster Postgres — that one is only ever
reached through the Kubernetes API.
"""

import logging

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings

log = logging.getLogger(__name__)

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    url = get_settings().supabase_db_url
    if not url:
        log.warning("SUPABASE_DB_URL not set; database features disabled")
        return
    # prepare_threshold=None: Supabase's pooler does not support prepared statements.
    _pool = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"row_factory": dict_row, "prepare_threshold": None},
    )
    await _pool.open(wait=False)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database is not configured (SUPABASE_DB_URL is empty)")
    return _pool
