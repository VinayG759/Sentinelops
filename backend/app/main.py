"""App entry point: create the app, mount routers, start/stop shared resources.

Adding a feature = create app/features/<name>/router.py and mount it below.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import db, health
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    await db.open_pool()
    yield
    await db.close_pool()


app = FastAPI(title="SentinelOps AI", version="0.1.0", lifespan=lifespan)

app.include_router(health.router)
