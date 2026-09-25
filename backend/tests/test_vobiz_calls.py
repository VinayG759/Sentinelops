"""The on-call phone alert: Vobiz webhooks and the call script (no network, no telephony)."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.integrations.vobiz import calls

SECRET = "s3cret-path-token"
PROPOSAL = {"id": uuid4(), "incident_id": "inc-1", "action": "set_service_port",
            "fs_change_id": 31}
OUTAGE = [{"id": "inc-1", "service": "order-service"},
          {"id": "inc-2", "service": "payment-service"}]


@pytest.fixture
def api(monkeypatch):
    s = calls.get_settings()
    monkeypatch.setattr(s, "vobiz_webhook_secret", SECRET)
    monkeypatch.setattr(s, "public_api_url", "https://tunnel.example")
    acknowledged = []

    async def get_proposal(pid):
        return PROPOSAL

    async def get_incident(iid):
        return {"id": iid, "fs_ticket_id": 89}

    async def incidents_on_ticket(tid):
        return OUTAGE

    async def transition(iid, to, actor):
        acknowledged.append((iid, to, actor))

    monkeypatch.setattr(calls.remediation, "get_proposal", get_proposal)
    monkeypatch.setattr(calls.incidents, "get_incident", get_incident)
    monkeypatch.setattr(calls.incidents, "incidents_on_ticket", incidents_on_ticket)
    monkeypatch.setattr(calls.incidents, "transition", transition)
    app = FastAPI()
    app.include_router(calls.router)
    return TestClient(app), acknowledged


def test_wrong_secret_is_rejected(api):
    client, _ = api
    assert client.post(f"/api/vobiz/wrong/answer/{PROPOSAL['id']}").status_code == 404


def test_answer_reads_the_outage_and_offers_the_menu(api):
    client, _ = api
    resp = client.post(f"/api/vobiz/{SECRET}/answer/{PROPOSAL['id']}")
    xml = resp.text
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/xml")
    assert "order-service and payment-service are failing" in xml
    assert "Change 31 in Freshservice is waiting for your approval" in xml
    assert '<Gather numDigits="1"' in xml and "Press 1 to acknowledge" in xml
    assert f"https://tunnel.example/api/vobiz/{SECRET}/gather/" in xml


def test_pressing_1_acknowledges_every_incident_of_the_outage(api):
    client, acknowledged = api
    resp = client.post(f"/api/vobiz/{SECRET}/gather/{PROPOSAL['id']}", data={"Digits": "1"})
    assert "Acknowledged" in resp.text and "<Hangup/>" in resp.text
    assert acknowledged == [("inc-1", "acknowledged", "phone:on-call"),
                            ("inc-2", "acknowledged", "phone:on-call")]


def test_pressing_2_repeats_and_nothing_else_changes_anything(api):
    client, acknowledged = api
    again = client.post(f"/api/vobiz/{SECRET}/gather/{PROPOSAL['id']}", data={"Digits": "2"})
    assert "<Redirect" in again.text and "/answer/" in again.text
    client.post(f"/api/vobiz/{SECRET}/gather/{PROPOSAL['id']}", data={"Digits": "9"})
    assert acknowledged == []
