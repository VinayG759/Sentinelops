"""Phone the on-call engineer when a fix is waiting for approval.

A ticket can sit unnoticed; a ringing phone can't. At most one call per 5 minutes, and it
summarises everything open when answered (a few services by name, then "and N more"; how
many fixes await approval, and where), so 100 failing services still mean one short call.
Press 1 acknowledges what was announced, 2 repeats. Approving stays in Freshservice /
SentinelOps, where the approver is logged in: anyone can pick up a phone.

Vobiz cannot authenticate to our API, so its webhooks sit under a secret path segment.
"""

import asyncio
import hmac
import logging
import time
from urllib.parse import parse_qs
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response

from app.core import events
from app.core.config import get_settings
from app.features.incidents import service as incidents
from app.features.remediation import service as remediation
from app.integrations.elevenlabs import tts
from app.integrations.vobiz import client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vobiz/{secret}", include_in_schema=False)

# Vobiz accepts exactly WOMAN or MAN (upper case); anything else is 'Invalid Answer XML'.
VOICE = 'voice="WOMAN" language="en-US"'

# At most one call per window: a big outage proposes many fixes, but the engineer needs one
# call that summarises everything open, not one call per fix.
CALL_COOLDOWN_SECONDS = 300
NAMED_SERVICES = 4  # read out by name; beyond this the call says "and N more"
_last_call_at: float | None = None


@events.on("remediation.proposed")
async def call_oncall(event: events.Event) -> None:
    if not client.configured():
        return
    global _last_call_at
    now = time.monotonic()
    if _last_call_at is not None and now - _last_call_at < CALL_COOLDOWN_SECONDS:
        return  # a recent call already covers this: its script is built when answered
    if not await incidents.list_incidents("triggered"):
        return  # everything open is already acknowledged: someone owns it, don't page again
    _last_call_at = now
    proposal_id = event["payload"]["proposal_id"]
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


async def _open_incidents() -> list[dict]:
    return await incidents.list_incidents("triggered") + await incidents.list_incidents(
        "acknowledged")


def spoken_services(names: list[str]) -> str:
    """'a, b and c' - or, past NAMED_SERVICES, 'a, b, c and 94 more'."""
    if len(names) <= NAMED_SERVICES:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    shown = NAMED_SERVICES - 1
    return ", ".join(names[:shown]) + f" and {len(names) - shown} more"


async def script(proposal_id: UUID) -> str:
    """What the engineer hears, built from live data at the moment they answer: everything
    open right now, however many services, in a call of about twenty seconds."""
    services = sorted({r["service"] for r in await _open_incidents()})
    pending = await remediation.list_proposals("pending")
    if not services:
        return "SentinelOps alert. The outage has already recovered. No action is needed."
    count = (f"{len(services)} services are failing, including " if len(services) > NAMED_SERVICES
             else "")
    verb = "is" if len(services) == 1 else "are"
    failing = (f"{count}{spoken_services(services)}." if count
               else f"{spoken_services(services)} {verb} failing.")
    if len(pending) == 1 and pending[0].get("fs_change_id"):
        ask = f"Change {pending[0]['fs_change_id']} in Freshservice is waiting for your approval."
    elif pending:
        ask = (f"{len(pending)} fixes are waiting for your approval. "
               "Review them in Freshservice, under Changes.")
    else:
        ask = "The AI is still investigating. Details are in Freshservice."
    return f"SentinelOps alert. {failing} {ask}"


@router.post("/answer/{proposal_id}")
async def answer(secret: str, proposal_id: UUID) -> Response:
    _check(secret)
    text = await script(proposal_id) + " Press 1 to acknowledge. Press 2 to hear this again."
    prompt, bye = await asyncio.gather(_voice(text), _voice("No input received. Goodbye."))
    action = f"{client.webhook_base()}/gather/{proposal_id}"
    return _xml(
        f'<Gather numDigits="1" executionTimeout="10" action="{action}" method="POST" '
        f'inputType="dtmf">{prompt}</Gather>{bye}'
    )


async def _voice(text: str) -> str:
    """<Play> an ElevenLabs recording of `text`, or <Speak> it if that is unavailable."""
    key = await tts.synthesize(text)
    if key:
        return f"<Play>{client.webhook_base()}/audio/{key}.mp3</Play>"
    return f"<Speak {VOICE}>{escape(text)}</Speak>"


@router.get("/audio/{key}.mp3")
async def audio(secret: str, key: str) -> Response:
    _check(secret)
    data = tts.cached(key)
    if data is None:
        raise HTTPException(404)
    return Response(data, media_type="audio/mpeg")


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
        return _xml(f"{await _voice('Goodbye.')}<Hangup/>")
    # Acknowledge exactly what the call announced: everything still untouched.
    for row in await incidents.list_incidents("triggered"):
        await incidents.transition(row["id"], "acknowledged", "phone:on-call")
    ack = await _voice("Acknowledged. Please review the changes in Freshservice. Goodbye.")
    return _xml(f"{ack}<Hangup/>")


@router.post("/hangup/{proposal_id}")
async def hangup(secret: str, proposal_id: UUID) -> Response:
    _check(secret)
    return Response(status_code=204)
