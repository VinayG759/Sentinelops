"""Proposals and approvals: the gate between the agent and the cluster.

Execution is never triggered from here directly. Approving emits `remediation.approved`,
and the executor listens for that event — so there is no HTTP path to the cluster.
"""

import asyncio
import logging
from uuid import UUID

from psycopg.types.json import Jsonb

from app.core import events
from app.core.db import get_pool
from app.features.remediation import actions, policy

log = logging.getLogger(__name__)

PROPOSAL_COLUMNS = (
    "id, incident_id, action, params, rationale, risk, approvals_required, status, "
    "fs_change_id, created_at, expires_at"
)


async def autonomy_paused() -> bool:
    async with get_pool().connection() as conn:
        row = await (await conn.execute("select autonomy_paused from public.settings")).fetchone()
    return bool(row["autonomy_paused"])


async def set_autonomy_paused(paused: bool, actor: str) -> bool:
    async with get_pool().connection() as conn:
        await conn.execute("update public.settings set autonomy_paused = %s", (paused,))
    await events.emit("autonomy.paused" if paused else "autonomy.resumed", actor, {})
    return paused


class AlreadyProposed(Exception):
    """A fix changing the same thing is already waiting for a human (or about to run)."""

    def __init__(self, proposal: dict):
        self.proposal = proposal
        super().__init__(f"proposal {proposal['id']} already changes the same target")


async def _open_for_same_target(action: actions.Action, params) -> dict | None:
    """One outage often opens several incidents, and each investigation may pick a slightly
    different value (e.g. max_connections 50 vs 100). Two proposals changing the same target
    would show a human two cards and patch production twice, so the first one stands."""
    target = action.target(params)
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                f"select {PROPOSAL_COLUMNS} from public.proposals "
                "where status in ('pending', 'approved') and expires_at > now() and action = %s "
                "order by created_at",
                (action.name,),
            )
        ).fetchall()
    for row in rows:
        try:
            _, existing = actions.validate(row["action"], row["params"])
        except (actions.NotAllowed, ValueError):
            continue
        if action.target(existing) == target:
            return row
    return None


async def propose(incident_id: UUID, action_name: str, raw_params: dict, rationale: str) -> dict:
    """Validate and record a proposal. Raises actions.NotAllowed / ValidationError if rejected."""
    action, params = actions.validate(action_name, raw_params)
    existing = await _open_for_same_target(action, params)
    if existing:
        raise AlreadyProposed(existing)

    decision = policy.decide(action, params)
    preview = await asyncio.to_thread(action.preview, params)

    async with get_pool().connection() as conn:
        proposal = await (
            await conn.execute(
                f"""insert into public.proposals
                    (incident_id, action, params, rationale, risk, approvals_required)
                    values (%s, %s, %s, %s, %s, %s) returning {PROPOSAL_COLUMNS}""",
                (incident_id, action.name, Jsonb(params.model_dump()), rationale,
                 decision.risk, decision.approvals_required),
            )
        ).fetchone()
        event = await events.insert(
            conn, "remediation.proposed", "agent",
            {
                "proposal_id": str(proposal["id"]),
                "action": action.name,
                "title": action.title,
                "params": params.model_dump(),
                "risk": decision.risk,
                "approvals_required": decision.approvals_required,
                "policy_reasons": decision.reasons,
                "preview": preview,
                "affected_services": action.affected_services(params),
                "rollback_plan": action.rollback_plan(params),
                "verify_query": action.verify_query(params),
                "rationale": rationale,
            },
            incident_id,
        )
    events.dispatch(event)
    return proposal


async def list_proposals(status: str | None = None) -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            f"select {PROPOSAL_COLUMNS} from public.proposals "
            "where %(status)s::text is null or status = %(status)s "
            "order by created_at desc limit 100",
            {"status": status},
        )
        return await cur.fetchall()


async def get_proposal(proposal_id: UUID) -> dict | None:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            f"select {PROPOSAL_COLUMNS} from public.proposals where id = %s", (proposal_id,)
        )
        return await cur.fetchone()


async def set_fs_change(proposal_id: UUID, change_id: int) -> None:
    """Remember the Freshservice change that mirrors this proposal."""
    async with get_pool().connection() as conn:
        await conn.execute(
            "update public.proposals set fs_change_id = %s where id = %s", (change_id, proposal_id)
        )


async def pending_with_fs_change() -> list[dict]:
    """Proposals still waiting for a human that have a Freshservice change to watch."""
    async with get_pool().connection() as conn:
        return await (
            await conn.execute(
                f"select {PROPOSAL_COLUMNS} from public.proposals "
                "where status = 'pending' and expires_at > now() and fs_change_id is not null"
            )
        ).fetchall()


async def decide_proposal(proposal_id: UUID, decision: str, user_id: str, reason: str) -> dict:
    """Approve or reject, atomically. Raises ValueError if it was already decided or expired.

    The UPDATE ... WHERE status='pending' is what makes a double-click safe: the second
    caller updates zero rows and gets an error instead of a second execution.
    """
    actor = f"user:{user_id}"
    new_status = "approved" if decision == "approved" else "rejected"

    async with get_pool().connection() as conn:
        proposal = await (
            await conn.execute(
                f"""update public.proposals set status = %s
                    where id = %s and status = 'pending' and expires_at > now()
                    returning {PROPOSAL_COLUMNS}""",
                (new_status, proposal_id),
            )
        ).fetchone()
        if proposal is None:
            raise ValueError("Proposal is not pending (already decided, or expired)")

        await conn.execute(
            "insert into public.approvals (proposal_id, user_id, decision, reason) "
            "values (%s, %s, %s, %s)",
            (proposal_id, user_id, new_status, reason),
        )
        event = await events.insert(
            conn, f"remediation.{new_status}", actor,
            {"proposal_id": str(proposal_id), "action": proposal["action"], "reason": reason},
            proposal["incident_id"],
        )
    events.dispatch(event)  # the executor listens for remediation.approved
    return proposal


async def supersede(proposal_id: UUID) -> None:
    """Retire an approved proposal because another change to the same target won. Marked
    expired (not rejected: no human said no) so the executor's sweep never retries it."""
    async with get_pool().connection() as conn:
        await conn.execute(
            "update public.proposals set status = 'expired' where id = %s and status = 'approved'",
            (proposal_id,),
        )


async def expire_stale_proposals() -> None:
    """Mark timed-out proposals expired so the UI stops offering them."""
    async with get_pool().connection() as conn:
        rows = await (
            await conn.execute(
                "update public.proposals set status = 'expired' "
                "where status = 'pending' and expires_at <= now() "
                "returning id, incident_id, action"
            )
        ).fetchall()
        for row in rows:
            event = await events.insert(
                conn, "remediation.expired", "system",
                {"proposal_id": str(row["id"]), "action": row["action"]}, row["incident_id"],
            )
            events.dispatch(event)


def catalog_summary() -> list[dict]:
    """The action catalog, for the UI and for the agent's tool description."""
    return [
        {
            "name": action.name,
            "title": action.title,
            "description": action.description,
            "parameters": action.Params.model_json_schema().get("properties", {}),
        }
        for action in actions.CATALOG.values()
    ]


async def approval_card(proposal: dict) -> dict:
    """Everything a human needs to decide: what changes, who it affects, how to undo it."""
    action, params = actions.validate(proposal["action"], proposal["params"])
    decision = policy.decide(action, params)
    try:
        preview = await asyncio.wait_for(asyncio.to_thread(action.preview, params), timeout=6)
    except Exception as exc:  # the cluster may be mid-restart; the card still renders
        log.warning("preview failed", extra={"proposal_id": str(proposal["id"])})
        preview = {"summary": "preview unavailable", "error": str(exc), "changes": []}

    return {
        "title": action.title,
        "description": action.description,
        "preview": preview,
        "affected_services": action.affected_services(params),
        "rollback_plan": action.rollback_plan(params),
        "verify_query": action.verify_query(params),
        "policy_reasons": decision.reasons,
    }
