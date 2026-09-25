"""The on-call phone alert: Vobiz webhooks and the call script (no network, no telephony)."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.vobiz import calls

SECRET = "s3cret-path-token"
PID = uuid4()


@pytest.fixture
def world(monkeypatch):
    s = calls.get_settings()
    monkeypatch.setattr(s, "vobiz_webhook_secret", SECRET)
    monkeypatch.setattr(s, "public_api_url", "https://tunnel.example")
    state = {
        "triggered": [{"id": "inc-1", "service": "order-service"},
                      {"id": "inc-2", "service": "payment-service"}],
        "acknowledged": [],
        "pending": [{"id": PID, "fs_change_id": 31}],
        "transitions": [],
    }

    async def list_incidents(status):
        return state.get(status, [])

    async def list_proposals(status=None):
        return state["pending"]

    async def transition(iid, to, actor):
        state["transitions"].append((iid, to, actor))

    monkeypatch.setattr(calls.incidents, "list_incidents", list_incidents)
    monkeypatch.setattr(calls.remediation, "list_proposals", list_proposals)
    monkeypatch.setattr(calls.incidents, "transition", transition)
    app = FastAPI()
    app.include_router(calls.router)
    return TestClient(app), state


def test_wrong_secret_is_rejected(world):
    client, _ = world
    assert client.post(f"/api/vobiz/wrong/answer/{PID}").status_code == 404


def test_answer_reads_the_outage_and_offers_the_menu(world):
    client, _ = world
    resp = client.post(f"/api/vobiz/{SECRET}/answer/{PID}")
    xml = resp.text
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/xml")
    assert "order-service and payment-service are failing" in xml
    assert "Change 31 in Freshservice is waiting for your approval" in xml
    assert '<Gather numDigits="1"' in xml and "Press 1 to acknowledge" in xml
    assert f"https://tunnel.example/api/vobiz/{SECRET}/gather/" in xml


async def test_a_hundred_failing_services_still_make_one_short_sentence(world):
    _, state = world
    state["triggered"] = [{"id": f"i{n}", "service": f"svc-{n:03d}"} for n in range(100)]
    state["pending"] = [{"id": n, "fs_change_id": n} for n in range(12)]
    text = await calls.script(PID)
    assert "100 services are failing, including svc-000, svc-001, svc-002 and 97 more" in text
    assert "12 fixes are waiting for your approval. Review them in Freshservice" in text
    assert "svc-050" not in text


def test_pressing_1_acknowledges_everything_announced(world):
    client, state = world
    resp = client.post(f"/api/vobiz/{SECRET}/gather/{PID}", data={"Digits": "1"})
    assert "Acknowledged" in resp.text and "<Hangup/>" in resp.text
    assert state["transitions"] == [("inc-1", "acknowledged", "phone:on-call"),
                                    ("inc-2", "acknowledged", "phone:on-call")]


def test_pressing_2_repeats_and_nothing_else_changes_anything(world):
    client, state = world
    again = client.post(f"/api/vobiz/{SECRET}/gather/{PID}", data={"Digits": "2"})
    assert "<Redirect" in again.text and "/answer/" in again.text
    client.post(f"/api/vobiz/{SECRET}/gather/{PID}", data={"Digits": "9"})
    assert state["transitions"] == []


async def test_one_call_per_window_and_none_once_acknowledged(monkeypatch):
    placed = []

    async def place_call(to, answer_url, hangup_url):
        placed.append(answer_url)
        return "call-1"

    async def emit(*args, **kwargs):
        return None

    monkeypatch.setattr(calls.client, "configured", lambda: True)
    monkeypatch.setattr(calls.client, "webhook_base", lambda: "https://t/api/vobiz/x")
    monkeypatch.setattr(calls.client, "place_call", place_call)
    monkeypatch.setattr(calls.events, "emit", emit)
    monkeypatch.setattr(calls, "_last_call_at", None)
    open_triggered = [{"id": "i1", "service": "order-service"}]

    async def list_incidents(status):
        return open_triggered if status == "triggered" else []

    monkeypatch.setattr(calls.incidents, "list_incidents", list_incidents)
    for n in range(5):  # a big outage proposes several fixes in quick succession
        await calls.call_oncall({"incident_id": f"i{n}", "payload": {"proposal_id": str(n)}})
    assert len(placed) == 1

    # Past the window, but everything open is acknowledged: nobody is paged again.
    monkeypatch.setattr(calls, "_last_call_at", None)
    open_triggered.clear()
    await calls.call_oncall({"incident_id": "i9", "payload": {"proposal_id": "9"}})
    assert len(placed) == 1
