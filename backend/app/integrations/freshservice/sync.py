"""Mirror SentinelOps events into Freshservice, the system of record IT teams already use.

Subscribers only: nothing here is called directly, and a Freshservice outage never blocks
the incident loop. A failed sync is recorded as `integration.failed` on the incident's
timeline; a successful one as `integration.synced`.
"""

import asyncio
import datetime as dt
import html
import logging

from app.core import events
from app.core.config import get_settings
from app.features.incidents import service as incidents
from app.features.remediation import service as remediation
from app.integrations.freshservice import client

log = logging.getLogger(__name__)

# Freshservice priority: 1 Low, 2 Medium, 3 High, 4 Urgent.
PRIORITY = {"sev1": 4, "sev2": 3, "sev3": 2}

# Incidents opened this close together share one ticket: one outage, one ticket.
OUTAGE_WINDOW_SECONDS = 120

# Sibling incidents open within the same second; without this, both would look for a
# ticket, find none, and each create one.
_ticket_lock = asyncio.Lock()


def _incident_link(incident_id) -> str:
    url = f"{get_settings().app_url}/incidents/{incident_id}"
    return f'<a href="{url}">{html.escape(url)}</a>'


def ticket_description(payload: dict, incident_id) -> str:
    esc = lambda v: html.escape(str(v))  # noqa: E731
    rows = [
        ("Service", payload.get("service")),
        ("Signal", payload.get("signal")),
        ("Error ratio", f"{payload['error_ratio']:.1%}" if "error_ratio" in payload else None),
        ("Requests/s", payload.get("request_rate")),
        ("Alert threshold", f"{payload['threshold']:.0%}" if "threshold" in payload else None),
    ]
    table = "".join(f"<li><b>{esc(k)}:</b> {esc(v)}</li>" for k, v in rows if v is not None)
    return (
        "<p>Opened automatically by <b>SentinelOps AI</b> from live Prometheus metrics.</p>"
        f"<ul>{table}</ul>"
        f"<p>Query: <code>{esc(payload.get('promql', ''))}</code></p>"
        "<p>The AI investigation, proposed fix and approvals follow in SentinelOps: "
        f"{_incident_link(incident_id)}</p>"
    )


@events.on("incident.opened")
async def ticket_for_incident(event: events.Event) -> None:
    if not client.configured():
        return
    incident_id, payload = event["incident_id"], event["payload"]
    try:
        async with _ticket_lock:
            existing = await incidents.open_ticket_for_outage(incident_id, OUTAGE_WINDOW_SECONDS)
            if existing:
                ticket_id, step = existing["fs_ticket_id"], "joined_ticket"
                await incidents.set_fs_ticket(incident_id, ticket_id)
                await _join_ticket(ticket_id, payload, incident_id)
            else:
                ticket_id, step = await client.create_ticket(
                    subject=f"[SentinelOps] {payload.get('title', 'Incident')}",
                    description_html=ticket_description(payload, incident_id),
                    priority=PRIORITY.get(payload.get("severity"), 2),
                ), "create_ticket"
                await incidents.set_fs_ticket(incident_id, ticket_id)
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": "ticket",
                           "error": str(exc)}, incident_id)
        return
    await events.emit("integration.synced", "system",
                      {"integration": "freshservice", "step": step,
                       "ticket_id": ticket_id, "url": client.ticket_url(ticket_id)}, incident_id)


async def _join_ticket(ticket_id: int, payload: dict, incident_id) -> None:
    """A second service failing in the same outage: note it on the outage's ticket, name
    every affected service in the subject, and raise the priority if this one is worse."""
    ratio = payload.get("error_ratio")
    await client.add_note(ticket_id, (
        f"<p><b>Also affected: {html.escape(str(payload.get('service')))}</b>"
        + (f" — {ratio:.0%} of requests failing" if ratio is not None else "")
        + ". Grouped into this ticket because it opened within "
        f"{OUTAGE_WINDOW_SECONDS // 60} minutes of the first incident (correlated by time; "
        "the investigation confirms whether the cause is shared).</p>"
        f"<p>{_incident_link(incident_id)}</p>"
    ))
    on_ticket = await incidents.incidents_on_ticket(ticket_id)
    services = sorted({row["service"] for row in on_ticket})
    priority = max(PRIORITY.get(row["severity"], 2) for row in on_ticket)
    await client.update_ticket(ticket_id, {
        "subject": f"[SentinelOps] Outage: {', '.join(services)} failing",
        "priority": priority,
    })


# Freshservice change risk: 1 Low, 2 Medium, 3 High, 4 Very High.
RISK = {"low": 1, "medium": 2, "high": 3}


def _iso(t: dt.datetime) -> str:
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def change_description(p: dict, incident_id, ticket_id: int | None) -> str:
    esc = lambda v: html.escape(str(v))  # noqa: E731
    changes = (p.get("preview") or {}).get("changes") or []
    diff = "".join(
        f"<li><code>{esc(c.get('field'))}</code>: {esc(c.get('from'))} &rarr; "
        f"<b>{esc(c.get('to'))}</b></li>" for c in changes
    ) or f"<li>{esc((p.get('preview') or {}).get('summary', 'see SentinelOps'))}</li>"
    reasons = "".join(f"<li>{esc(r)}</li>" for r in p.get("policy_reasons") or [])
    ticket = f" (ticket #{ticket_id})" if ticket_id else ""
    return (
        f"<p>Proposed by <b>SentinelOps AI</b> to fix an ongoing outage{ticket}. "
        "The AI can only choose from a fixed catalog of safe actions; SentinelOps validated "
        "this one against its allow-list and policy.</p>"
        f"<h3>Why</h3><p>{esc(p.get('rationale', ''))}</p>"
        f"<h3>What will change</h3><ul>{diff}</ul>"
        f"<h3>Risk</h3><p>{esc(p.get('risk'))} risk &middot; "
        f"{esc(p.get('approvals_required'))} approval(s) required</p><ul>{reasons}</ul>"
        f"<h3>Affected services</h3><p>{esc(', '.join(p.get('affected_services') or []))}</p>"
        f"<h3>How success is checked</h3><p>For up to 2 minutes after the change: "
        f"<code>{esc(p.get('verify_query', ''))}</code></p>"
        f"<h3>How it is undone</h3><p>{esc(p.get('rollback_plan', ''))} "
        "&mdash; automatically, if the check fails.</p>"
        "<h3>Approve here</h3><p>Approve or reject this change in Freshservice. SentinelOps "
        "applies it within about 15 seconds of approval, re-checking its safety rules first "
        "(kill switch, allow-list), then verifies recovery.</p>"
        f"<p>Investigate in SentinelOps: {_incident_link(incident_id)}</p>"
    )


@events.on("remediation.proposed")
async def change_for_proposal(event: events.Event) -> None:
    if not client.configured():
        return
    incident_id, p = event["incident_id"], event["payload"]
    incident = await incidents.get_incident(incident_id)
    ticket_id = incident.get("fs_ticket_id") if incident else None
    params = ", ".join(f"{k}={v}" for k, v in (p.get("params") or {}).items())
    now = dt.datetime.now(dt.UTC)
    try:
        change_id = await client.create_change(
            subject=f"[SentinelOps] {p.get('title', p.get('action'))}: {params}",
            description_html=change_description(p, incident_id, ticket_id),
            risk=RISK.get(p.get("risk"), 2),
            priority=PRIORITY.get(incident["severity"], 2) if incident else 3,
            planned_start=_iso(now + dt.timedelta(minutes=1)),
            planned_end=_iso(now + dt.timedelta(minutes=31)),
        )
        await remediation.set_fs_change(p["proposal_id"], change_id)
        if ticket_id:
            await client.add_note(ticket_id, (
                f"<p><b>Fix proposed:</b> {html.escape(str(p.get('title')))} "
                f"({html.escape(params)})"
                f" &mdash; change <a href=\"{client.change_url(change_id)}\">#CHN-{change_id}</a>"
                " is awaiting approval. Nothing runs until it is approved.</p>"
            ))
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": "create_change",
                           "error": str(exc)}, incident_id)
        return
    await events.emit("integration.synced", "system",
                      {"integration": "freshservice", "step": "create_change",
                       "change_id": change_id, "url": client.change_url(change_id)}, incident_id)


APPROVAL_POLL_SECONDS = 15


def decision_from(approvals: list[dict]) -> tuple[str, dict] | None:
    """('approved' | 'rejected', the approval) once any approver in Freshservice decided.
    A rejection wins over an approval: when in doubt, don't act."""
    by_status = {(a.get("approval_status") or {}).get("name", "").lower(): a for a in approvals}
    for status in ("rejected", "approved"):
        if status in by_status:
            return status, by_status[status]
    return None


async def watch_change_approvals() -> None:
    """Every 15s, read the Freshservice approvals of changes SentinelOps is waiting on, and
    record a decision taken there. The decision goes through the same atomic transition as
    one taken in SentinelOps, so approving in both places can never run the fix twice."""
    while True:
        await asyncio.sleep(APPROVAL_POLL_SECONDS)
        if not client.configured():
            continue
        try:
            for proposal in await remediation.pending_with_fs_change():
                found = decision_from(await client.change_approvals(proposal["fs_change_id"]))
                if not found:
                    continue
                decision, approval = found
                who = approval.get("approver_name") or f"agent {approval.get('approver_id')}"
                remark = approval.get("latest_remark") or ""
                try:
                    await remediation.decide_proposal(
                        proposal["id"], decision, None,
                        f"{decision} in Freshservice change #{proposal['fs_change_id']} by {who}"
                        + (f": {remark}" if remark else ""),
                        source="freshservice", actor=f"freshservice:{who}",
                    )
                except ValueError:
                    pass  # decided in SentinelOps meanwhile, or expired
        except Exception:
            log.exception("freshservice approval watch failed")
