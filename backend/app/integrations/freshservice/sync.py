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
from app.features.remediation import actions
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


def _button(url: str, label: str, primary: bool = True) -> str:
    """A link styled as a button (Freshservice keeps inline styles in descriptions/notes)."""
    colours = ("background:#2563eb;color:#ffffff" if primary
               else "background:#ffffff;color:#1f2937;border:1px solid #d1d5db")
    return (f'<a href="{html.escape(url)}" style="display:inline-block;padding:8px 14px;'
            f'{colours};border-radius:6px;text-decoration:none;font-weight:600;'
            f'margin:4px 8px 4px 0">{html.escape(label)}</a>')


def investigate_button(incident_id, primary: bool = False) -> str:
    return _button(f"{get_settings().app_url}/incidents/{incident_id}",
                   "Investigate in SentinelOps", primary)


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
        "<p>SentinelOps is investigating now. When it proposes a fix, a note here will link "
        "to the change to approve.</p>"
        f"<p>{investigate_button(incident_id, primary=True)}</p>"
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
        f"<p>{investigate_button(incident_id)}</p>"
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


def _row(label: str, value_html: str) -> str:
    return (
        '<tr><td style="padding:4px 12px 4px 0;color:#6b7280;white-space:nowrap">'
        f"{label}</td><td style=\"padding:4px 0\">{value_html}</td></tr>"
    )


def _target(p: dict) -> str | None:
    try:
        action, params = actions.validate(p.get("action", ""), p.get("params") or {})
    except Exception:
        return None
    return action.target(params)


def change_description(p: dict, incident_id, ticket_id: int | None) -> str:
    """The change as an approver reads it: a summary table first, the reasoning in plain
    words, how success is judged, and the technical detail last."""
    esc = lambda v: html.escape(str(v))  # noqa: E731
    preview = p.get("preview") or {}
    diff = "<br>".join(
        f"<code>{esc(c.get('field'))}</code>: {esc(c.get('from'))} &rarr; "
        f"<b>{esc(c.get('to'))}</b>" for c in preview.get("changes") or []
    ) or esc(preview.get("summary") or "see SentinelOps")
    services = p.get("affected_services") or []
    risk = str(p.get("risk", "")).capitalize()
    n = p.get("approvals_required", 1)
    summary = "".join([
        _row("Action", f"<b>{esc(p.get('title', p.get('action')))}</b>"),
        _row("Target", f"<code>{esc(_target(p) or '-')}</code>"),
        _row("Change", diff),
        _row("Risk", f"{esc(risk)} &middot; {esc(n)} approval{'s' if n != 1 else ''} needed"),
        _row("Affects", esc(", ".join(services) or "-")),
        _row("If it fails", "Automatically undone: " + esc(p.get("rollback_plan", ""))),
    ])
    who = " and ".join(services) or "the affected services"
    reasons = "; ".join(p.get("policy_reasons") or []) or "-"
    return (
        "<p><b>SentinelOps AI</b> proposes this fix for an ongoing outage. It could only "
        "choose from a fixed catalog of safe actions, and SentinelOps has checked it against "
        "its allow-list and approval policy.</p>"
        f"<table>{summary}</table>"
        f"<p><b>Why</b><br>{esc(p.get('rationale', ''))}</p>"
        f"<p><b>How we will know it worked</b><br>Error rate on {esc(who)} back below 2%, "
        "checked every 10 seconds for up to 2 minutes after the change.</p>"
        "<p><b>To approve</b><br>Use Approve / Reject on this change. SentinelOps applies it "
        "within about 15 seconds of approval, after re-checking its kill switch and "
        "allow-list, then verifies recovery.</p>"
        f"<p>{investigate_button(incident_id)}"
        + (_button(client.ticket_url(ticket_id), f"Outage ticket #{ticket_id}", primary=False)
           if ticket_id else "")
        + "</p>"
        '<p style="color:#6b7280;font-size:12px">Technical detail &mdash; verification query: '
        f"<code>{esc(p.get('verify_query', ''))}</code><br>Policy: {esc(reasons)}</p>"
    )


def action_needed_note(title, params: str, change_id: int, incident_id) -> str:
    """The note that tells whoever reads the ticket what to do next: approvals live on the
    change, not on this ticket."""
    return (
        '<div style="border-left:4px solid #f59e0b;padding:4px 12px">'
        "<p><b>Action needed: approve the fix</b></p>"
        f"<p>SentinelOps AI proposes: <b>{html.escape(str(title))}</b> "
        f"({html.escape(params)}). Nothing changes until someone approves it.</p>"
        f"<p>Approval happens on the <b>change</b> #CHN-{change_id}, not on this ticket: "
        "open it and use Approve or Reject. SentinelOps applies an approved fix within "
        "about 15 seconds and posts the result here.</p>"
        f"<p>{_button(client.change_url(change_id), f'Review & approve change #CHN-{change_id}')}"
        f"{investigate_button(incident_id)}</p></div>"
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
            await client.add_note(ticket_id, action_needed_note(
                p.get("title"), params, change_id, incident_id))
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


# --- Closing the loop: what happened after the change was approved -----------------------

CHANGE_CLOSED = 6  # Freshservice change status
TICKET_RESOLVED, TICKET_CLOSED = 4, 5


async def _records_for(event: events.Event) -> tuple[int | None, int | None]:
    """(ticket id, change id) mirroring the event's incident and proposal, if any."""
    incident = await incidents.get_incident(event["incident_id"]) if event["incident_id"] else None
    proposal_id = (event["payload"] or {}).get("proposal_id")
    proposal = await remediation.get_proposal(proposal_id) if proposal_id else None
    return (incident or {}).get("fs_ticket_id"), (proposal or {}).get("fs_change_id")


async def _note_both(event: events.Event, step: str, body: str, close_change: bool = False):
    if not client.configured():
        return
    ticket_id, change_id = await _records_for(event)
    try:
        if ticket_id:
            await client.add_note(ticket_id, body)
        if change_id:
            await client.request("POST", f"/changes/{change_id}/notes", {"body": body})
            if close_change:
                await client.request("PUT", f"/changes/{change_id}", {"status": CHANGE_CLOSED})
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": step, "error": str(exc)},
                          event["incident_id"])


def _when(event: events.Event) -> str:
    created = event.get("created_at")
    return created.strftime("%H:%M:%S UTC") if isinstance(created, dt.datetime) else "now"


@events.on("execution.succeeded")
async def note_applied(event: events.Event) -> None:
    before = html.escape(str((event["payload"] or {}).get("before", "")))
    await _note_both(event, "note_applied",
                     f"<p><b>Change applied</b> at {_when(event)} (state before: "
                     f"<code>{before}</code>). Verifying recovery for up to 2 minutes&hellip;</p>")


@events.on("verification.passed")
async def note_verified(event: events.Event) -> None:
    await _note_both(event, "close_change",
                     f"<p><b>Recovery verified</b> at {_when(event)}: the error rate is back "
                     "below 2%. Change closed by SentinelOps.</p>", close_change=True)


@events.on("rollback.succeeded")
async def note_rolled_back(event: events.Event) -> None:
    await _note_both(event, "note_rollback",
                     "<p><b>The change did not restore service and was rolled back "
                     f"automatically</b> at {_when(event)}. The outage is still open; "
                     "SentinelOps keeps investigating.</p>")


@events.on("execution.failed")
async def note_failed(event: events.Event) -> None:
    error = html.escape(str((event["payload"] or {}).get("error", "")))
    await _note_both(event, "note_failed",
                     f"<p><b>Applying the change failed</b>: {error}. Nothing was changed.</p>")


@events.on("remediation.rejected")
async def note_rejected(event: events.Event) -> None:
    if (event["payload"] or {}).get("source") == "freshservice":
        return  # decided in Freshservice: it already shows there
    reason = html.escape(str((event["payload"] or {}).get("reason") or "no reason given"))
    await _note_both(event, "note_rejected",
                     f"<p><b>Rejected in SentinelOps</b>: {reason}. Nothing will run.</p>",
                     close_change=True)


def _duration(start: dt.datetime | None, end: dt.datetime | None) -> str:
    if not start or not end:
        return "-"
    s = int((end - start).total_seconds())
    return f"{s}s" if s < 90 else f"{s // 60}m {s % 60}s"


async def resolution_summary(on_ticket: list[dict]) -> str:
    """Root cause, fix, approver and timings, from the event log of the ticket's incidents."""
    esc = lambda v: html.escape(str(v))  # noqa: E731
    evs = [e for row in on_ticket for e in await incidents.incident_events(row["id"])]
    first = lambda t: next((e for e in evs if e["type"] == t), None)  # noqa: E731
    opened, found = first("incident.opened"), first("investigation.completed")
    proposed, approved = first("remediation.proposed"), first("remediation.approved")
    applied, verified = first("execution.succeeded"), first("verification.passed")
    t0 = opened["created_at"] if opened else None
    at = lambda e: e["created_at"] if e else None  # noqa: E731
    rows = "".join([
        _row("Root cause", esc(found["payload"].get("hypothesis")) if found else "-"),
        _row("Fix", esc(proposed["payload"].get("title")) + " (" + esc(", ".join(
            f"{k}={v}" for k, v in (proposed["payload"].get("params") or {}).items())) + ")"
             if proposed else "-"),
        _row("Approved by", esc(approved["actor"].replace("user:", "SentinelOps user ")
                                .replace("freshservice:", "") + (
            " (in Freshservice)" if approved["payload"].get("source") == "freshservice"
            else " (in SentinelOps)")) if approved else "-"),
        _row("Services", esc(", ".join(sorted({r["service"] for r in on_ticket})))),
        _row("Timeline", " &middot; ".join([
            f"root cause in {_duration(t0, at(found))}",
            f"approved at +{_duration(t0, at(approved))}",
            f"applied at +{_duration(t0, at(applied))}",
            f"verified at +{_duration(t0, at(verified))}",
        ])),
    ])
    return ("<p><b>Resolved by SentinelOps AI</b> &mdash; the approved change was applied "
            "and recovery verified from live metrics.</p>" f"<table>{rows}</table>")


@events.on("incident.resolved")
async def resolve_ticket(event: events.Event) -> None:
    """Resolve the ticket once every incident grouped on it is resolved."""
    if not client.configured():
        return
    incident = await incidents.get_incident(event["incident_id"])
    ticket_id = (incident or {}).get("fs_ticket_id")
    if not ticket_id:
        return
    try:
        async with _ticket_lock:  # sibling incidents resolve in the same second
            on_ticket = await incidents.incidents_on_ticket(ticket_id)
            open_ids = [r for r in on_ticket if r["id"] != incident["id"]]
            still_open = [r for r in open_ids if (await incidents.get_incident(r["id"]))
                          ["status"] != "resolved"]
            if still_open:
                return
            status = (await client.request("GET", f"/tickets/{ticket_id}"))["ticket"]["status"]
            if status in (TICKET_RESOLVED, TICKET_CLOSED):
                return
            await client.add_note(ticket_id, await resolution_summary(on_ticket))
            await client.update_ticket(ticket_id, {"status": TICKET_RESOLVED})
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": "resolve_ticket",
                           "error": str(exc)}, event["incident_id"])
        return
    await events.emit("integration.synced", "system",
                      {"integration": "freshservice", "step": "resolve_ticket",
                       "ticket_id": ticket_id, "url": client.ticket_url(ticket_id)},
                      event["incident_id"])


@events.on("incident.acknowledged")
async def note_acknowledged(event: events.Event) -> None:
    """Someone owns the outage now, e.g. the on-call engineer pressed 1 on the alert call."""
    actor = event["actor"]
    who = ("the on-call engineer, by phone (SentinelOps alert call)" if actor.startswith("phone:")
           else "a responder in SentinelOps")
    ticket_id, _ = await _records_for(event)
    if not ticket_id or not client.configured():
        return
    try:
        await client.add_note(ticket_id, f"<p><b>Acknowledged</b> by {who} at {_when(event)}.</p>")
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": "note_acknowledged",
                           "error": str(exc)}, event["incident_id"])
