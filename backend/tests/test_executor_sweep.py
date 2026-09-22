"""The sweeper catches approvals whose event was lost (e.g. a backend restart)."""

import asyncio
from uuid import uuid4

import pytest

from app.features.remediation import executor


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, *args, **kwargs):
        return FakeCursor(self.rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, rows):
        self.rows = rows

    def connection(self):
        return FakeConnection(self.rows)


@pytest.fixture
def swept(monkeypatch):
    ran: list = []

    async def fake_run(proposal_id):
        ran.append(proposal_id)

    monkeypatch.setattr(executor, "run", fake_run)
    monkeypatch.setattr(executor, "SWEEP_SECONDS", 0.01)
    return ran


async def run_one_sweep(rows, swept):
    """Run the loop just long enough for a single pass."""
    monkeyed_pool = FakePool(rows)
    import app.features.remediation.executor as module

    original = module.get_pool
    module.get_pool = lambda: monkeyed_pool
    try:
        task = asyncio.create_task(executor.sweep())
        await asyncio.sleep(0.05)
        task.cancel()
    finally:
        module.get_pool = original
    return swept


async def test_sweeper_executes_orphaned_approvals(swept):
    proposal_id = uuid4()
    await run_one_sweep([{"id": proposal_id}], swept)
    assert proposal_id in swept


async def test_sweeper_does_nothing_when_all_approvals_ran(swept):
    await run_one_sweep([], swept)
    assert swept == []


async def test_sweeper_survives_a_database_error(swept, monkeypatch):
    class Broken:
        def connection(self):
            raise RuntimeError("database unreachable")

    import app.features.remediation.executor as module

    original = module.get_pool
    module.get_pool = lambda: Broken()
    try:
        task = asyncio.create_task(executor.sweep())
        await asyncio.sleep(0.05)
        assert not task.done(), "the loop must keep running after an error"
        task.cancel()
    finally:
        module.get_pool = original
