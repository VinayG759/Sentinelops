"""App entry point: create the app, mount routers, start/stop shared resources.

Adding a feature = create app/features/<name>/router.py and mount it below.
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import auth, db, health
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.features.audit.router import router as audit_router
from app.features.incidents import detector
from app.features.incidents.router import events_router
from app.features.incidents.router import router as incidents_router
from app.features.investigation.router import router as investigation_router
from app.features.remediation import executor
from app.features.remediation.router import router as remediation_router
from app.features.simulator.router import router as simulator_router
from app.features.topology.router import router as topology_router
from app.integrations.freshservice import (
    sync as freshservice_sync,  # noqa: F401  (registers subscribers)
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    await db.open_pool()
    background = []
    if get_settings().supabase_db_url:
        background.append(asyncio.create_task(detector.run()))
        background.append(asyncio.create_task(executor.sweep()))
    yield
    for task in background:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await db.close_pool()


app = FastAPI(title="SentinelOps AI", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(incidents_router)
app.include_router(audit_router)
app.include_router(events_router)
app.include_router(investigation_router)
app.include_router(remediation_router)
app.include_router(simulator_router)
app.include_router(topology_router)
