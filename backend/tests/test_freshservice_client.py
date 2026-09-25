"""Freshservice client and ticket mapping, against recorded responses (no network)."""

import httpx
import pytest
import respx

from app.integrations.freshservice import client, sync

BASE = "https://example.freshservice.com/api/v2"


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    s = client.get_settings()
    monkeypatch.setattr(s, "freshservice_domain", "example.freshservice.com")
    monkeypatch.setattr(s, "freshservice_api_key", "test-key")
    monkeypatch.setattr(client, "_requester_email", "agent@example.com")
    monkeypatch.setattr(client, "_workspace_id", 21)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(client.asyncio, "sleep", no_sleep)


@respx.mock
async def test_create_ticket_sends_requester_priority_and_open_status():
    route = respx.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(201, json={"ticket": {"id": 42, "priority": 4}})
    )
    assert await client.create_ticket("s", "<p>d</p>", priority=4) == 42
    sent = route.calls.last.request
    body = httpx.Response(200, content=sent.content).json()
    assert body == {"subject": "s", "description": "<p>d</p>",
                    "email": "agent@example.com", "priority": 4, "status": 2,
                    "source": 14, "workspace_id": 21}
    assert sent.headers["authorization"].startswith("Basic ")


@respx.mock
async def test_priority_reset_by_a_workspace_rule_is_set_again():
    respx.post(f"{BASE}/tickets").mock(
        return_value=httpx.Response(201, json={"ticket": {"id": 7, "priority": 1}})
    )
    fix = respx.put(f"{BASE}/tickets/7").mock(return_value=httpx.Response(200, json={}))
    await client.create_ticket("s", "d", priority=3)
    assert fix.called and b'"priority":3' in fix.calls.last.request.content.replace(b" ", b"")


@respx.mock
async def test_rate_limit_is_retried_then_succeeds():
    route = respx.get(f"{BASE}/tickets").mock(side_effect=[
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"tickets": []}),
    ])
    assert await client.request("GET", "/tickets") == {"tickets": []}
    assert route.call_count == 2


@respx.mock
async def test_client_errors_are_not_retried():
    route = respx.get(f"{BASE}/tickets").mock(return_value=httpx.Response(403, json={}))
    with pytest.raises(client.FreshserviceError, match="403"):
        await client.request("GET", "/tickets")
    assert route.call_count == 1


@respx.mock
async def test_server_errors_give_up_after_the_retries():
    route = respx.get(f"{BASE}/tickets").mock(return_value=httpx.Response(503))
    with pytest.raises(client.FreshserviceError):
        await client.request("GET", "/tickets")
    assert route.call_count == client.ATTEMPTS


def test_severity_maps_to_freshservice_priority():
    assert sync.PRIORITY == {"sev1": 4, "sev2": 3, "sev3": 2}


def test_ticket_description_escapes_and_links_back():
    html = sync.ticket_description(
        {"service": "order-service", "error_ratio": 0.52, "threshold": 0.05,
         "promql": "a < b"}, "abc")
    assert "52.0%" in html and "5%" in html
    assert "a &lt; b" in html, "PromQL must be HTML-escaped"
    assert "/incidents/abc" in html


def test_change_description_shows_the_diff_risk_rollback_and_escapes():
    html = sync.change_description({
        "rationale": "port <5433> is wrong",
        "preview": {"changes": [{"field": "spec.ports[0].port", "from": 5433, "to": 5432}]},
        "risk": "medium", "approvals_required": 1, "policy_reasons": ["touches a Service"],
        "affected_services": ["order-service", "payment-service"],
        "verify_query": "x < bool 0.02", "rollback_plan": "Put the port back",
    }, "inc-1", 89)
    assert "5433 &rarr; <b>5432</b>" in html
    assert "order-service and payment-service back below 2%" in html
    assert "port &lt;5433&gt; is wrong" in html, "AI text must be escaped"
    assert "Outage ticket #89" in html and "Put the port back" in html
    assert "/incidents/inc-1" in html
    assert sync.RISK == {"low": 1, "medium": 2, "high": 3}


def _approval(name, who="Vinay G"):
    return {"approval_status": {"id": 0, "name": name}, "approver_name": who}


def test_freshservice_approval_decisions():
    assert sync.decision_from([]) is None
    assert sync.decision_from([_approval("requested")]) is None, "still waiting"
    assert sync.decision_from([_approval("Approved")])[0] == "approved"
    both = [_approval("approved", "A"), _approval("rejected", "B")]
    assert sync.decision_from(both) == ("rejected", both[1]), "when in doubt, don't act"
