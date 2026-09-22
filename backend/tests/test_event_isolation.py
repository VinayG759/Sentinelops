"""One subscriber crashing must not stop the others, and must be recorded."""

import asyncio
from collections import defaultdict

from app.core import events


async def test_failing_subscriber_does_not_affect_others(monkeypatch):
    calls: list[str] = []
    recorded: list[tuple] = []

    async def fake_emit(type, actor, payload=None, incident_id=None):
        recorded.append((type, payload))

    monkeypatch.setattr(events, "emit", fake_emit)
    monkeypatch.setattr(events, "_subscribers", defaultdict(list))

    @events.on("test.happened")
    async def broken(event):
        raise ValueError("boom")

    @events.on("test.happened")
    async def healthy(event):
        calls.append("healthy ran")

    events.dispatch({"id": 1, "type": "test.happened", "incident_id": None})
    await asyncio.gather(*events._running)

    assert calls == ["healthy ran"]
    assert recorded[0][0] == "handler.failed"
    assert "boom" in recorded[0][1]["error"]


async def test_failure_report_failing_does_not_loop(monkeypatch):
    recorded: list[str] = []

    async def fake_emit(type, *args, **kwargs):
        recorded.append(type)

    monkeypatch.setattr(events, "emit", fake_emit)
    monkeypatch.setattr(events, "_subscribers", defaultdict(list))

    @events.on("handler.failed")
    async def broken(event):
        raise ValueError("boom")

    events.dispatch({"id": 2, "type": "handler.failed", "incident_id": None})
    await asyncio.gather(*events._running)

    assert recorded == []
