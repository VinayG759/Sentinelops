"""The investigation agent: Claude, given read-only tools and a hard rule about evidence.

Every tool call becomes an `investigation.step` event, and the event's id is handed back
to the model as `evidence_id`. The final finding must cite those ids, so each claim on the
timeline links to the exact observation behind it.
"""

import asyncio
import json
import logging
import time

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.core import events
from app.core.config import get_settings
from app.features.investigation.schemas import SUBMIT_TOOL, Finding
from app.features.investigation.tools import TOOL_SCHEMAS, run_tool

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5"
MAX_TOOL_CALLS = 14
TIME_BUDGET_SECONDS = 120
MAX_TOKENS = 2000

SYSTEM_PROMPT = """You are SentinelOps, an SRE agent investigating a live incident on a \
small Kubernetes system.

Services: order-service and payment-service (Node.js, each with a Postgres connection pool), \
postgres (the database), prometheus (metrics). Both services query the database continuously; \
failures show up as error-rate spikes.

How to work:
- Investigate with the read-only tools. You cannot change anything.
- Start from the failing service's metrics and logs, then follow the evidence: configuration, \
the Kubernetes Service it connects to, recent rollouts, connectivity.
- Prefer a cause you can demonstrate over one that merely sounds likely. If logs show \
connection timeouts, prove where the connection goes and whether that port is open; if they \
show connection refusals or "too many clients", check the database's own settings and the \
pool gauges. The postgres component has logs too.
- Note what you ruled out.
- Once the cause is proven, if an action in the catalog would fix it, call propose_remediation. \
You cannot run anything: a human reviews and approves every proposal. Propose nothing if no \
catalogued action fits, and say so in your finding instead.
- Finish by calling submit_finding, citing the evidence_id of each tool result you relied on.
- Be concise. Do not repeat a tool call with identical arguments."""


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key)


def _incident_brief(incident: dict, opening_event: dict | None) -> str:
    detail = json.dumps(opening_event.get("payload", {}), default=str) if opening_event else "{}"
    return (
        f"Incident {incident['id']}\n"
        f"Service: {incident['service']}\n"
        f"Signal: {incident['signal']} (severity {incident['severity']})\n"
        f"Title: {incident['title']}\n"
        f"Opened at: {incident['opened_at']}\n"
        f"Detector evidence: {detail}\n\n"
        "Investigate and report the root cause."
    )


async def investigate(incident: dict, opening_event: dict | None = None) -> dict | None:
    """Run one investigation. Returns the validated finding, or None if it could not finish."""
    incident_id = incident["id"]
    started = time.monotonic()
    await events.emit(
        "investigation.started", "agent", {"model": MODEL, "service": incident["service"]},
        incident_id,
    )

    client = _client()
    messages: list[dict] = [{"role": "user", "content": _incident_brief(incident, opening_event)}]
    tools = [*TOOL_SCHEMAS, _propose_tool(), SUBMIT_TOOL]
    calls_made = 0
    correction_used = False
    usage = {"input_tokens": 0, "output_tokens": 0}

    try:
        while True:
            if calls_made >= MAX_TOOL_CALLS:
                return await _fail(incident_id, f"tool call limit ({MAX_TOOL_CALLS}) reached")
            if time.monotonic() - started > TIME_BUDGET_SECONDS:
                return await _fail(incident_id, f"time budget ({TIME_BUDGET_SECONDS}s) exceeded")

            response = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            usage["input_tokens"] += response.usage.input_tokens
            usage["output_tokens"] += response.usage.output_tokens
            messages.append({"role": "assistant", "content": response.content})
            blocks = [b for b in response.content if b.type == "tool_use"]
            if not blocks:
                return await _fail(incident_id, "agent stopped without calling submit_finding")

            results = []
            for block in blocks:
                if block.name == "submit_finding":
                    finding, error = _validate(block.input)
                    if finding:
                        await events.emit(
                            "investigation.completed", "agent",
                            finding.model_dump() | {"tool_calls": calls_made,
                                                    "seconds": round(time.monotonic() - started),
                                                    "usage": usage},
                            incident_id,
                        )
                        return finding.model_dump()
                    if correction_used:
                        return await _fail(incident_id, f"invalid finding: {error}")
                    correction_used = True
                    results.append(_tool_result(block.id, f"REJECTED: {error}. Fix and resubmit.",
                                                is_error=True))
                    continue

                if block.name == "propose_remediation":
                    results.append(await _propose(incident_id, block))
                    continue

                calls_made += 1
                results.append(await _run_step(incident_id, block))

            messages.append({"role": "user", "content": results})
    except Exception as exc:
        log.exception("investigation crashed", extra={"incident_id": str(incident_id)})
        return await _fail(incident_id, f"{type(exc).__name__}: {exc}")


def _propose_tool() -> dict:
    """Describe the action catalog to the model, generated from the catalog itself."""
    from app.features.remediation.service import catalog_summary

    catalogue = "\n".join(
        f"- {a['name']}: {a['description']} Parameters: {list(a['parameters'])}"
        for a in catalog_summary()
    )
    return {
        "name": "propose_remediation",
        "description": (
            "Propose a fix for a human to approve. You may only choose from this catalog; "
            "free-form commands are impossible.\n" + catalogue
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action name from the catalog"},
                "params": {"type": "object", "description": "Parameters for that action"},
                "rationale": {
                    "type": "string",
                    "description": "Why this fixes the proven cause, in one or two sentences",
                },
            },
            "required": ["action", "params", "rationale"],
        },
    }


async def _propose(incident_id, block) -> dict:
    """Validate and record a proposal. Rejections are returned to the model, not hidden."""
    from app.features.remediation import service as remediation

    args = dict(block.input)
    try:
        proposal = await remediation.propose(
            incident_id, args.get("action", ""), args.get("params") or {},
            args.get("rationale", ""),
        )
        body = json.dumps({"status": "awaiting human approval", "proposal_id": str(proposal["id"]),
                           "risk": proposal["risk"]})
        return _tool_result(block.id, body)
    except Exception as exc:
        log.warning("proposal rejected", extra={"incident_id": str(incident_id), "error": str(exc)})
        await events.emit(
            "remediation.rejected_by_policy", "system",
            {"action": args.get("action"), "params": args.get("params"), "error": str(exc)},
            incident_id,
        )
        return _tool_result(block.id, f"REJECTED: {exc}", is_error=True)


async def _run_step(incident_id, block) -> dict:
    """Run one tool, record it as evidence, and hand the model back its evidence_id."""
    try:
        output = await asyncio.wait_for(run_tool(block.name, dict(block.input)), timeout=30)
        ok = True
    except Exception as exc:
        output = json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        ok = False

    event = await events.emit(
        "investigation.step", "agent",
        {"tool": block.name, "args": dict(block.input), "result": output[:4000], "ok": ok},
        incident_id,
    )
    payload = json.dumps({"evidence_id": event["id"], "result": json.loads(output)})
    return _tool_result(block.id, payload, is_error=not ok)


def _tool_result(tool_use_id: str, content: str, is_error: bool = False) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


def _validate(raw: dict) -> tuple[Finding | None, str]:
    try:
        return Finding(**raw), ""
    except ValidationError as exc:
        return None, "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())


async def _fail(incident_id, reason: str) -> None:
    log.warning("investigation failed", extra={"incident_id": str(incident_id), "reason": reason})
    await events.emit("investigation.failed", "agent", {"reason": reason}, incident_id)
    return None


@events.on("incident.opened")
async def _investigate_new_incident(event: events.Event) -> None:
    from app.features.incidents import service  # local import keeps module import order simple

    if not get_settings().anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY not set; skipping investigation")
        return
    incident = await service.get_incident(event["incident_id"])
    if incident:
        await investigate(incident, event)
