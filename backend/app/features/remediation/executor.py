"""Execute an approved remediation, verify it worked, and undo it if it didn't.

Triggered only by the `remediation.approved` event — there is no HTTP route into this
module, so an approval is the only way a change reaches the cluster.

Before acting it re-checks, in order: kill switch, proposal status, allow-list. Any doubt
means no execution ("fail closed"). The `executions` table has a unique constraint on
proposal_id, so even two simultaneous approvals produce at most one run.
"""

import asyncio
import logging
from uuid import UUID

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.core import events, prometheus
from app.core.db import get_pool
from app.features.incidents import service as incidents
from app.features.remediation import actions, service

log = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 120
VERIFY_INTERVAL_SECONDS = 10
SETTLE_SECONDS = 15  # let the change take effect before the first check


SWEEP_SECONDS = 30


@events.on("remediation.approved")
async def _on_approved(event: events.Event) -> None:
    await run(UUID(event["payload"]["proposal_id"]))


async def sweep() -> None:
    """Safety net: execute approvals whose event nobody acted on.

    The event bus is in-process, so an approval recorded while this process was
    restarting (or by another process) would otherwise sit there forever. Claiming is
    atomic, so a swept proposal can never be executed twice.
    """
    while True:
        try:
            async with get_pool().connection() as conn:
                rows = await (
                    await conn.execute(
                        "select p.id from public.proposals p "
                        "left join public.executions e on e.proposal_id = p.id "
                        "where p.status = 'approved' and e.id is null"
                    )
                ).fetchall()
            for row in rows:
                log.warning("sweeping unexecuted approval", extra={"proposal_id": str(row["id"])})
                await run(row["id"])
        except Exception:
            log.exception("executor sweep failed")
        await asyncio.sleep(SWEEP_SECONDS)


async def run(proposal_id: UUID) -> None:
    proposal = await service.get_proposal(proposal_id)
    if proposal is None:
        return log.error("proposal vanished", extra={"proposal_id": str(proposal_id)})

    incident_id = proposal["incident_id"]
    refusal = await _refusal_reason(proposal)
    if refusal:
        await events.emit("execution.refused", "system",
                          {"proposal_id": str(proposal_id), "reason": refusal}, incident_id)
        return log.warning("execution refused", extra={"reason": refusal})

    try:
        action, params = actions.validate(proposal["action"], proposal["params"])
    except (actions.NotAllowed, ValueError) as exc:
        await events.emit("execution.refused", "system",
                          {"proposal_id": str(proposal_id), "reason": str(exc)}, incident_id)
        return

    execution_id = await _claim(proposal_id)
    if execution_id is None:
        return log.warning("already executed", extra={"proposal_id": str(proposal_id)})

    await events.emit("execution.started", "system",
                      {"proposal_id": str(proposal_id), "action": action.name,
                       "params": proposal["params"]}, incident_id)

    try:
        before = await asyncio.to_thread(action.execute, params)
    except Exception as exc:
        await _finish(execution_id, "failed", result={"error": f"{type(exc).__name__}: {exc}"})
        await events.emit("execution.failed", "system",
                          {"proposal_id": str(proposal_id), "error": str(exc)}, incident_id)
        log.exception("execution failed", extra={"proposal_id": str(proposal_id)})
        return

    await _record_before(execution_id, before)
    await events.emit("execution.succeeded", "system",
                      {"proposal_id": str(proposal_id), "before": before}, incident_id)
    await _mark_proposal_executed(proposal_id)

    await _verify_or_rollback(execution_id, proposal, action, params, before)


async def _refusal_reason(proposal: dict) -> str | None:
    if await service.autonomy_paused():
        return "autonomy is paused (kill switch is on)"
    if proposal["status"] != "approved":
        return f"proposal status is '{proposal['status']}', not 'approved'"
    return None


async def _claim(proposal_id: UUID) -> UUID | None:
    """Insert the execution row; the unique constraint makes this a one-time claim."""
    async with get_pool().connection() as conn:
        try:
            row = await (
                await conn.execute(
                    "insert into public.executions (proposal_id) values (%s) returning id",
                    (proposal_id,),
                )
            ).fetchone()
        except UniqueViolation:
            return None
    return row["id"]


async def _record_before(execution_id: UUID, before: dict) -> None:
    async with get_pool().connection() as conn:
        await conn.execute(
            "update public.executions set before = %s where id = %s", (Jsonb(before), execution_id)
        )


async def _finish(execution_id: UUID, status: str, result: dict) -> None:
    async with get_pool().connection() as conn:
        await conn.execute(
            "update public.executions set status = %s, result = %s, finished_at = now() "
            "where id = %s",
            (status, Jsonb(result), execution_id),
        )


async def _mark_proposal_executed(proposal_id: UUID) -> None:
    async with get_pool().connection() as conn:
        await conn.execute(
            "update public.proposals set status = 'executed' where id = %s", (proposal_id,)
        )


async def _verify_or_rollback(execution_id, proposal, action, params, before) -> None:
    incident_id = proposal["incident_id"]
    query = action.verify_query(params)
    await asyncio.sleep(SETTLE_SECONDS)

    attempts = max(1, VERIFY_TIMEOUT_SECONDS // max(VERIFY_INTERVAL_SECONDS, 1))
    for _ in range(attempts):
        healthy = await _check(query)
        if healthy:
            await _finish(execution_id, "succeeded", {"verified": True, "query": query})
            await events.emit("verification.passed", "system",
                              {"proposal_id": str(proposal["id"]), "query": query}, incident_id)
            await incidents.transition(incident_id, "resolved", "system")
            return
        await asyncio.sleep(VERIFY_INTERVAL_SECONDS)

    await events.emit("verification.failed", "system",
                      {"proposal_id": str(proposal["id"]), "query": query,
                       "waited_seconds": VERIFY_TIMEOUT_SECONDS}, incident_id)
    await _rollback(execution_id, proposal, action, params, before)


async def _check(query: str) -> bool:
    """The verify query returns 1 when every affected service is healthy again."""
    try:
        value = await prometheus.query_scalar(query)
    except Exception:
        log.exception("verification query failed")
        return False
    return value == 1.0


async def _rollback(execution_id, proposal, action, params, before) -> None:
    incident_id = proposal["incident_id"]
    await events.emit("rollback.started", "system",
                      {"proposal_id": str(proposal["id"]), "before": before}, incident_id)
    try:
        restored = await asyncio.to_thread(action.rollback, params, before)
    except Exception as exc:
        await _finish(execution_id, "failed", {"rollback_error": str(exc)})
        await events.emit("rollback.failed", "system",
                          {"proposal_id": str(proposal["id"]), "error": str(exc)}, incident_id)
        log.exception("rollback failed", extra={"proposal_id": str(proposal["id"])})
        return

    await _finish(execution_id, "rolled_back", {"restored": restored})
    await events.emit("rollback.succeeded", "system",
                      {"proposal_id": str(proposal["id"]), "restored": restored}, incident_id)
    # Back to a human: the fix did not work and has been undone.
    await incidents.transition(incident_id, "triggered", "system")
