"""Mirror SentinelOps events into Freshservice, the system of record IT teams already use.

Subscribers only: nothing here is called directly, and a Freshservice outage never blocks
the incident loop. A failed sync is recorded as `integration.failed` on the incident's
timeline; a successful one as `integration.synced`.
"""

import asyncio
import html
import logging

from app.core import events
from app.core.config import get_settings
from app.features.incidents import service as incidents
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
