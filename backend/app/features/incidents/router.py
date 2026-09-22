from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import Role, User, current_user, require_role
from app.features.incidents import service
from app.features.incidents.schemas import Event, Incident, Status

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
events_router = APIRouter(prefix="/api/events", tags=["incidents"])


@events_router.get("", response_model=list[Event])
async def recent_events(limit: int = 20, _: User = Depends(current_user)):
    """The newest events across all incidents — the activity feed on the overview."""
    return await service.recent_events(min(limit, 100))


@router.get("", response_model=list[Incident])
async def list_incidents(status: Status | None = None, _: User = Depends(current_user)):
    return await service.list_incidents(status)


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: UUID, _: User = Depends(current_user)):
    incident = await service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return incident


@router.get("/{incident_id}/events", response_model=list[Event])
async def get_events(incident_id: UUID, _: User = Depends(current_user)):
    return await service.incident_events(incident_id)


@router.get("/{incident_id}/metrics")
async def get_metrics(incident_id: UUID, minutes: int = 30, _: User = Depends(current_user)):
    """Error ratio, request rate and p95 latency around the incident, for the charts."""
    incident = await service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return await service.incident_metrics(incident, minutes)


@router.post("/{incident_id}/acknowledge", response_model=Incident)
async def acknowledge(incident_id: UUID, user: User = Depends(require_role(Role.responder))):
    return await _transition(incident_id, "acknowledged", user)


@router.post("/{incident_id}/resolve", response_model=Incident)
async def resolve(incident_id: UUID, user: User = Depends(require_role(Role.responder))):
    return await _transition(incident_id, "resolved", user)


async def _transition(incident_id: UUID, to: str, user: User) -> dict:
    incident = await service.transition(incident_id, to, f"user:{user.id}")
    if incident is None:
        raise HTTPException(409, f"Incident not found or cannot move to '{to}'")
    return incident
