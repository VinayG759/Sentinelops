import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import Role, User, require_role
from app.features.incidents import service
from app.features.investigation import agent

router = APIRouter(prefix="/api/incidents", tags=["investigation"])

_running: set[asyncio.Task] = set()  # keep references so tasks are not garbage-collected


@router.post("/{incident_id}/investigate")
async def investigate(incident_id: UUID, _: User = Depends(require_role(Role.responder))):
    """Re-run the investigation. It also runs automatically when an incident opens."""
    incident = await service.get_incident(incident_id)
    if incident is None:
        raise HTTPException(404, "Incident not found")
    # Returns immediately; progress appears on the timeline as investigation.step events.
    task = asyncio.create_task(agent.investigate(incident))
    _running.add(task)
    task.add_done_callback(_running.discard)
    return {"status": "started", "incident_id": str(incident_id)}
