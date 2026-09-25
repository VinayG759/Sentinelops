"""Phone the on-call engineer when a fix is waiting for approval.

A ticket can sit unnoticed; a ringing phone can't. The call reads the situation (what is
failing, what the AI proposes, which change to approve) and offers: press 1 to acknowledge,
2 to repeat. Approving stays in Freshservice / SentinelOps, where the approver is logged in:
anyone can pick up a phone.

Vobiz cannot authenticate to our API, so its webhooks sit under a secret path segment.
"""

import hmac
import logging
from urllib.parse import parse_qs
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response

from app.core import events
from app.core.config import get_settings
from app.features.incidents import service as incidents
from app.features.remediation import service as remediation
from app.integrations.vobiz import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vobiz/{secret}", include_in_schema=False)

VOICE = 'voice="woman" language="en-US"'
_called: set[str] = set()  # one call per proposal, even if the event is seen twice


@events.on("remediation.proposed")
async def call_oncall(event: events.Event) -> None:
    if not client.configured():
        return
    proposal_id = event["payload"]["proposal_id"]
    if proposal_id in _called:
        return
    _called.add(proposal_id)
    base = client.webhook_base()
    try:
        call_id = await client.place_call(
            get_settings().oncall_phone,
            answer_url=f"{base}/answer/{proposal_id}",
            hangup_url=f"{base}/hangup/{proposal_id}",
        )
    except Exception as exc:  # a failed call must never block the incident loop
        await events.emit("notification.failed", "system",
                          {"channel": "phone", "error": str(exc)}, event["incident_id"])
        return
    await events.emit("notification.sent", "system",
                      {"channel": "phone", "to": "on-call", "call_id": call_id},
                      event["incident_id"])


def _check(secret: str) -> None:
    expected = get_settings().vobiz_webhook_secret
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(404)


def _xml(body: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
                    media_type="application/xml")


async def _outage(proposal: dict | None) -> list[dict]:
    """Every incident in the proposal's outage (grouped by Freshservice ticket if any)."""
    incident = await incidents.get_incident(proposal["incident_id"]) if proposal else None
    if not incident:
        return []
    if incident.get("fs_ticket_id"):
        return await incidents.incidents_on_ticket(incident["fs_ticket_id"])
    return [incident]


async def script(proposal_id: UUID) -> str:
    """What the engineer hears, built from live data at the moment they answer."""
    proposal = await remediation.get_proposal(proposal_id)
    if proposal is None:
        return "SentinelOps alert. The proposed fix could not be found."
    rows = await _outage(proposal)
    services = sorted({r["service"] for r in rows}) or ["a service"]
    verb = "are" if len(services) > 1 else "is"
    change = (f"Change {proposal['fs_change_id']} in Freshservice is waiting for your approval."
              if proposal.get("fs_change_id") else "A fix is waiting for your approval.")
    action = proposal["action"].replace("_", " ")
    return (f"SentinelOps alert. {' and '.join(services)} {verb} failing. "
            f"The AI has found the cause and proposes a fix: {action}. {change}")


@router.post("/answer/{proposal_id}")
async def answer(secret: str, proposal_id: UUID) -> Response:
    _check(secret)
    text = escape(await script(proposal_id))
    action = f"{client.webhook_base()}/gather/{proposal_id}"
    return _xml(
        f'<Gather numDigits="1" executionTimeout="10" action="{action}" method="POST" '
        f'inputType="dtmf"><Speak {VOICE}>{text} '
        "Press 1 to acknowledge. Press 2 to hear this again.</Speak></Gather>"
        f"<Speak {VOICE}>No input received. Goodbye.</Speak>"
    )


@router.post("/gather/{proposal_id}")
async def gather(secret: str, proposal_id: UUID, request: Request) -> Response:
    _check(secret)
    # Vobiz posts form-encoded fields; parsed by hand to avoid a multipart dependency.
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    digits = (form.get("Digits") or [""])[0]
    if digits == "2":
        return _xml(f'<Redirect method="POST">{client.webhook_base()}/answer/{proposal_id}'
                    "</Redirect>")
    if digits != "1":
        return _xml(f"<Speak {VOICE}>Goodbye.</Speak><Hangup/>")
    for row in await _outage(await remediation.get_proposal(proposal_id)):
        await incidents.transition(row["id"], "acknowledged", "phone:on-call")
    return _xml(f"<Speak {VOICE}>Acknowledged. Please review the change in Freshservice. "
                "Goodbye.</Speak><Hangup/>")


@router.post("/hangup/{proposal_id}")
async def hangup(secret: str, proposal_id: UUID) -> Response:
    _check(secret)
    return Response(status_code=204)
