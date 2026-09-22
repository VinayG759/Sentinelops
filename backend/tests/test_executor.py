"""The executor: refuses unless everything checks out, verifies, and rolls back on failure."""

from uuid import uuid4

import pytest

from app.features.remediation import executor

PROPOSAL = {
    "id": uuid4(),
    "incident_id": uuid4(),
    "action": "scale_service",
    "params": {"service": "order-service", "replicas": 3},
    "status": "approved",
    "risk": "low",
}


@pytest.fixture
def world(monkeypatch):
    """Fakes for everything the executor touches; returns the recorded calls."""
    state = {
        "events": [],
        "executed": [],
        "rolled_back": [],
        "claimed": True,
        "paused": False,
        "proposal": dict(PROPOSAL),
        "healthy": True,
        "transitions": [],
        "finished": [],
    }

    async def emit(type, actor, payload=None, incident_id=None):
        state["events"].append(type)
        return {"id": len(state["events"]), "type": type}

    async def get_proposal(pid):
        return state["proposal"]

    async def paused():
        return state["paused"]

    async def claim(pid):
        return uuid4() if state["claimed"] else None

    async def check(query):
        return state["healthy"]

    async def transition(incident_id, to, actor):
        state["transitions"].append(to)
        return {"status": to}

    async def finish(execution_id, status, result):
        state["finished"].append(status)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(executor.events, "emit", emit)
    monkeypatch.setattr(executor.service, "get_proposal", get_proposal)
    monkeypatch.setattr(executor.service, "autonomy_paused", paused)
    monkeypatch.setattr(executor, "_claim", claim)
    monkeypatch.setattr(executor, "_check", check)
    monkeypatch.setattr(executor, "_record_before", noop)
    monkeypatch.setattr(executor, "_mark_proposal_executed", noop)
    monkeypatch.setattr(executor, "_finish", finish)
    monkeypatch.setattr(executor.incidents, "transition", transition)
    monkeypatch.setattr(executor, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(executor, "VERIFY_INTERVAL_SECONDS", 0)

    class FakeAction:
        name = "scale_service"

        def execute(self, params):
            state["executed"].append(params)
            return {"replicas": 2}

        def rollback(self, params, before):
            state["rolled_back"].append(before)
            return before

        def verify_query(self, params):
            return "vector(1)"

    monkeypatch.setattr(executor.actions, "validate", lambda name, params: (FakeAction(), params))
    return state


async def test_happy_path_executes_verifies_and_resolves(world):
    await executor.run(PROPOSAL["id"])

    assert world["executed"], "the action should have run"
    assert world["events"] == [
        "execution.started", "execution.succeeded", "verification.passed",
    ]
    assert world["transitions"] == ["resolved"]
    assert world["rolled_back"] == []


async def test_kill_switch_blocks_execution(world):
    world["paused"] = True

    await executor.run(PROPOSAL["id"])

    assert world["executed"] == []
    assert world["events"] == ["execution.refused"]


@pytest.mark.parametrize("status", ["pending", "rejected", "expired", "executed"])
async def test_only_an_approved_proposal_executes(world, status):
    world["proposal"]["status"] = status

    await executor.run(PROPOSAL["id"])

    assert world["executed"] == []
    assert world["events"] == ["execution.refused"]


async def test_a_second_approval_cannot_execute_twice(world):
    world["claimed"] = False  # the executions row already exists

    await executor.run(PROPOSAL["id"])

    assert world["executed"] == []
    assert world["events"] == []


async def test_failed_verification_rolls_back_and_reopens_the_incident(world):
    world["healthy"] = False

    await executor.run(PROPOSAL["id"])

    assert world["executed"], "it still executed"
    assert world["rolled_back"] == [{"replicas": 2}], "and then undid it"
    assert world["events"] == [
        "execution.started", "execution.succeeded", "verification.failed",
        "rollback.started", "rollback.succeeded",
    ]
    assert world["transitions"] == ["triggered"], "handed back to a human"
    assert world["finished"] == ["rolled_back"]


async def test_execution_failure_is_recorded_and_does_not_verify(world, monkeypatch):
    class Exploding:
        name = "scale_service"

        def execute(self, params):
            raise RuntimeError("cluster unreachable")

        def verify_query(self, params):
            return "vector(1)"

    monkeypatch.setattr(executor.actions, "validate", lambda n, p: (Exploding(), p))

    await executor.run(PROPOSAL["id"])

    assert world["events"] == ["execution.started", "execution.failed"]
    assert world["finished"] == ["failed"]
