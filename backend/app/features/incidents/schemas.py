from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

Severity = Literal["sev1", "sev2", "sev3"]
Status = Literal["triggered", "acknowledged", "resolved"]


class Incident(BaseModel):
    id: UUID
    service: str
    signal: str
    severity: Severity
    status: Status
    title: str
    fs_ticket_id: int | None
    opened_at: datetime
    resolved_at: datetime | None


class Event(BaseModel):
    id: int
    incident_id: UUID | None
    type: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime
    hash: str
