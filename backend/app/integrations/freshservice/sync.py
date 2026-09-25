"""Mirror SentinelOps events into Freshservice, the system of record IT teams already use.

Subscribers only: nothing here is called directly, and a Freshservice outage never blocks
the incident loop. A failed sync is recorded as `integration.failed` on the incident's
timeline; a successful one as `integration.synced`.
"""

import html
import logging

from app.core import events
from app.core.config import get_settings
from app.features.incidents import service as incidents
from app.integrations.freshservice import client

log = logging.getLogger(__name__)

# Freshservice priority: 1 Low, 2 Medium, 3 High, 4 Urgent.
PRIORITY = {"sev1": 4, "sev2": 3, "sev3": 2}


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
        ticket_id = await client.create_ticket(
            subject=f"[SentinelOps] {payload.get('title', 'Incident')}",
            description_html=ticket_description(payload, incident_id),
            priority=PRIORITY.get(payload.get("severity"), 2),
        )
    except client.FreshserviceError as exc:
        await events.emit("integration.failed", "system",
                          {"integration": "freshservice", "step": "create_ticket",
                           "error": str(exc)}, incident_id)
        return
    await incidents.set_fs_ticket(incident_id, ticket_id)
    await events.emit("integration.synced", "system",
                      {"integration": "freshservice", "step": "create_ticket",
                       "ticket_id": ticket_id, "url": client.ticket_url(ticket_id)}, incident_id)
