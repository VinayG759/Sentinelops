"""One outage, one Freshservice ticket, even when sibling incidents open in the same second."""

import asyncio

import pytest

from app.integrations.freshservice import sync


@pytest.fixture
def fs(monkeypatch):
    rows = {}  # incident_id -> {"service", "severity", "fs_ticket_id"}
    calls = {"created": [], "notes": [], "updates": [], "events": []}

    async def open_ticket_for_outage(exclude_id, window):
        await asyncio.sleep(0)  # yield, as the real DB call does
        return next(({"fs_ticket_id": r["fs_ticket_id"], **r} for i, r in rows.items()
                     if i != exclude_id and r["fs_ticket_id"]), None)

    async def set_fs_ticket(incident_id, ticket_id):
        rows[incident_id]["fs_ticket_id"] = ticket_id

    async def incidents_on_ticket(ticket_id):
        return [r for r in rows.values() if r["fs_ticket_id"] == ticket_id]

    async def create_ticket(subject, description_html, priority):
        await asyncio.sleep(0)
        calls["created"].append((subject, priority))
        return 100 + len(calls["created"])

    async def add_note(ticket_id, body, private=True):
        calls["notes"].append((ticket_id, body))

    async def update_ticket(ticket_id, fields):
        calls["updates"].append((ticket_id, fields))

    async def emit(type, actor, payload=None, incident_id=None):
        calls["events"].append((type, payload.get("step")))

    monkeypatch.setattr(sync.client, "configured", lambda: True)
    monkeypatch.setattr(sync.client, "create_ticket", create_ticket)
    monkeypatch.setattr(sync.client, "add_note", add_note)
    monkeypatch.setattr(sync.client, "update_ticket", update_ticket)
    monkeypatch.setattr(sync.incidents, "open_ticket_for_outage", open_ticket_for_outage)
    monkeypatch.setattr(sync.incidents, "set_fs_ticket", set_fs_ticket)
    monkeypatch.setattr(sync.incidents, "incidents_on_ticket", incidents_on_ticket)
    monkeypatch.setattr(sync.events, "emit", emit)
    return rows, calls


def _opened(rows, incident_id, service, severity, ratio):
    rows[incident_id] = {"service": service, "severity": severity, "fs_ticket_id": None}
    return {"incident_id": incident_id, "payload": {
        "service": service, "severity": severity, "error_ratio": ratio,
        "title": f"{service}: {ratio:.0%} of requests failing"}}


async def test_sibling_incidents_opening_together_share_one_ticket(fs):
    rows, calls = fs
    await asyncio.gather(
        sync.ticket_for_incident(_opened(rows, "a", "order-service", "sev2", 0.39)),
        sync.ticket_for_incident(_opened(rows, "b", "payment-service", "sev1", 0.55)),
    )

    assert len(calls["created"]) == 1, "one outage must create exactly one ticket"
    assert rows["a"]["fs_ticket_id"] == rows["b"]["fs_ticket_id"]
    assert len(calls["notes"]) == 1 and "Also affected" in calls["notes"][0][1]
    subject, priority = calls["updates"][0][1]["subject"], calls["updates"][0][1]["priority"]
    assert "order-service" in subject and "payment-service" in subject
    assert priority == 4, "the worse incident (sev1) raises the ticket to Urgent"
    assert sorted(step for _, step in calls["events"]) == ["create_ticket", "joined_ticket"]


async def test_an_unrelated_incident_later_gets_its_own_ticket(fs, monkeypatch):
    rows, calls = fs

    async def nothing_open(exclude_id, window):
        return None

    monkeypatch.setattr(sync.incidents, "open_ticket_for_outage", nothing_open)
    await sync.ticket_for_incident(_opened(rows, "a", "order-service", "sev3", 0.1))
    await sync.ticket_for_incident(_opened(rows, "b", "payment-service", "sev3", 0.1))
    assert len(calls["created"]) == 2
