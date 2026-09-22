"""Agent loop rules, with a stand-in for Claude: no network, no cost.

Covered: evidence is compulsory, one correction is allowed, the tool-call cap and the
time budget end the run cleanly, and each tool call is recorded as evidence.
"""

from itertools import count
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.features.investigation import agent

INCIDENT = {
    "id": uuid4(),
    "service": "order-service",
    "signal": "error_rate",
    "severity": "sev1",
    "title": "order-service: 100% of requests failing",
    "opened_at": "2026-09-23T10:00:00Z",
}


def tool_use(name, payload, block_id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=payload, id=block_id)


def text(body="thinking"):
    return SimpleNamespace(type="text", text=body)


class FakeClaude:
    """Replays a scripted list of responses and records what it was sent."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(
            content=self.responses.pop(0),
            usage=SimpleNamespace(input_tokens=100, output_tokens=50),
        )


@pytest.fixture
def recorder(monkeypatch):
    """Capture emitted events; return the list."""
    emitted: list[tuple[str, dict]] = []
    next_id = iter(range(100, 200))

    async def fake_emit(type, actor, payload=None, incident_id=None):
        emitted.append((type, payload or {}))
        return {"id": next(next_id), "type": type, "incident_id": incident_id}

    monkeypatch.setattr(agent.events, "emit", fake_emit)
    return emitted


@pytest.fixture
def fake_tools(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def fake_run_tool(name, args):
        calls.append((name, args))
        return '{"error_ratio": 1.0}'

    monkeypatch.setattr(agent, "run_tool", fake_run_tool)
    return calls


def use_client(monkeypatch, client):
    monkeypatch.setattr(agent, "_client", lambda: client)


async def test_records_each_tool_call_then_returns_the_finding(monkeypatch, recorder, fake_tools):
    finding = {"hypothesis": "port mismatch", "confidence": "high", "evidence": [100],
               "ruled_out": ["pool exhaustion: waiting is 0"]}
    use_client(monkeypatch, FakeClaude(
        [tool_use("get_service_metrics", {"service": "order-service"})],
        [text(), tool_use("submit_finding", finding, "t2")],
    ))

    result = await agent.investigate(INCIDENT)

    assert result["hypothesis"] == "port mismatch"
    assert fake_tools == [("get_service_metrics", {"service": "order-service"})]
    completed = next(p for t, p in recorder if t == "investigation.completed")
    assert completed["usage"] == {"input_tokens": 200, "output_tokens": 100}  # summed per turn
    assert [t for t, _ in recorder] == [
        "investigation.started", "investigation.step", "investigation.completed",
    ]


async def test_finding_without_evidence_is_rejected_then_accepted_after_correction(
    monkeypatch, recorder, fake_tools
):
    use_client(monkeypatch, FakeClaude(
        [tool_use("submit_finding", {"hypothesis": "guess", "confidence": "high", "evidence": []})],
        [tool_use("submit_finding", {"hypothesis": "proven", "confidence": "high",
                                     "evidence": [100]}, "t2")],
    ))

    result = await agent.investigate(INCIDENT)

    assert result["hypothesis"] == "proven"
    assert "investigation.failed" not in [t for t, _ in recorder]


async def test_second_invalid_finding_fails_the_investigation(monkeypatch, recorder, fake_tools):
    bad = {"hypothesis": "guess", "confidence": "high", "evidence": []}
    use_client(monkeypatch, FakeClaude(
        [tool_use("submit_finding", bad)], [tool_use("submit_finding", bad, "t2")]
    ))

    assert await agent.investigate(INCIDENT) is None
    assert recorder[-1][0] == "investigation.failed"
    assert "evidence" in recorder[-1][1]["reason"]


async def test_tool_call_cap_ends_the_run(monkeypatch, recorder, fake_tools):
    monkeypatch.setattr(agent, "MAX_TOOL_CALLS", 3)
    one_call = [tool_use("get_logs", {"service": "order-service"})]
    use_client(monkeypatch, FakeClaude(*[one_call] * 4))

    assert await agent.investigate(INCIDENT) is None
    assert len(fake_tools) == 3
    assert "tool call limit" in recorder[-1][1]["reason"]


async def test_time_budget_ends_the_run(monkeypatch, recorder, fake_tools):
    ticks = count(0, agent.TIME_BUDGET_SECONDS)  # every check jumps a full budget forward
    monkeypatch.setattr(agent, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    use_client(monkeypatch, FakeClaude([tool_use("get_logs", {"service": "order-service"})]))

    assert await agent.investigate(INCIDENT) is None
    assert "time budget" in recorder[-1][1]["reason"]


async def test_stopping_without_a_finding_is_a_failure(monkeypatch, recorder, fake_tools):
    use_client(monkeypatch, FakeClaude([text("I give up")]))

    assert await agent.investigate(INCIDENT) is None
    assert "without calling submit_finding" in recorder[-1][1]["reason"]


async def test_a_failing_tool_does_not_crash_the_run(monkeypatch, recorder):
    async def boom(name, args):
        raise RuntimeError("kubernetes unreachable")

    monkeypatch.setattr(agent, "run_tool", boom)
    use_client(monkeypatch, FakeClaude(
        [tool_use("get_logs", {"service": "order-service"})],
        [tool_use("submit_finding", {"hypothesis": "h", "confidence": "low",
                                     "evidence": [100]}, "t2")],
    ))

    assert (await agent.investigate(INCIDENT))["confidence"] == "low"
    step = next(p for t, p in recorder if t == "investigation.step")
    assert step["ok"] is False
    assert "kubernetes unreachable" in step["result"]
