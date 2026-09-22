from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import Role, User, current_user, require_role
from app.features.remediation import service

router = APIRouter(tags=["remediation"])


class Proposal(BaseModel):
    id: UUID
    incident_id: UUID
    action: str
    params: dict[str, Any]
    rationale: str
    risk: Literal["low", "medium", "high"]
    approvals_required: int
    status: Literal["pending", "approved", "rejected", "expired", "executed"]
    created_at: datetime
    expires_at: datetime


class ProposalDetail(Proposal):
    title: str
    description: str
    preview: dict[str, Any]
    affected_services: list[str]
    rollback_plan: str
    verify_query: str
    policy_reasons: list[str]


class AutonomyState(BaseModel):
    paused: bool


@router.get("/api/proposals", response_model=list[Proposal])
async def list_proposals(status: str | None = None, _: User = Depends(current_user)):
    await service.expire_stale_proposals()
    return await service.list_proposals(status)


@router.get("/api/proposals/{proposal_id}", response_model=ProposalDetail)
async def get_proposal(proposal_id: UUID, _: User = Depends(current_user)):
    proposal = await service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "Proposal not found")
    return {**proposal, **await service.approval_card(proposal)}


@router.get("/api/actions")
async def list_actions(_: User = Depends(current_user)):
    """The action catalog: everything SentinelOps is able to do, and nothing else."""
    return service.catalog_summary()


@router.post("/api/proposals/{proposal_id}/{decision}", response_model=Proposal)
async def decide(
    proposal_id: UUID,
    decision: Literal["approve", "reject"],
    reason: str = Body("", embed=True),
    user: User = Depends(require_role(Role.approver)),
):
    """Approve or reject. Approving emits an event; the executor acts on that, not on this call."""
    try:
        return await service.decide_proposal(
            proposal_id, "approved" if decision == "approve" else "rejected", user.id, reason
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/api/settings/autonomy", response_model=AutonomyState)
async def get_autonomy(_: User = Depends(current_user)):
    return AutonomyState(paused=await service.autonomy_paused())


@router.post("/api/settings/autonomy", response_model=AutonomyState)
async def set_autonomy(
    state: AutonomyState, user: User = Depends(require_role(Role.admin))
) -> AutonomyState:
    paused = await service.set_autonomy_paused(state.paused, f"user:{user.id}")
    return AutonomyState(paused=paused)
