from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.auth import User, current_user
from app.features.audit import service
from app.features.audit.schemas import AuditEvent, ChainStatus

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/verify", response_model=ChainStatus)
async def verify(_: User = Depends(current_user)):
    """Recompute every event's hash. Green badge on the audit page; red names the broken row."""
    return await service.verify_chain()


@router.get("/events", response_model=list[AuditEvent])
async def events(
    limit: int = Query(service.DEFAULT_PAGE, ge=1, le=service.MAX_PAGE),
    before_id: int | None = Query(None, description="Page backwards: events older than this id"),
    incident_id: UUID | None = None,
    _: User = Depends(current_user),
):
    return await service.list_events(limit, before_id, incident_id)


@router.get("/export")
async def export(_: User = Depends(current_user)):
    """The whole chain as JSON lines, so it can be verified outside SentinelOps."""
    return StreamingResponse(
        service.export_lines(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="sentinelops-audit.jsonl"'},
    )
