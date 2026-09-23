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
    # The agent's latest conclusion; only filled in by the list endpoint.
    root_cause: str | None = None
    root_cause_confidence: Literal["low", "medium", "high"] | None = None
    investigation_failed_reason: str | None = None


class Event(BaseModel):
    id: int
    incident_id: UUID | None
    type: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime
    hash: str


class IncidentStats(BaseModel):
    """Outcome numbers for incidents opened in a time window. None = nothing to measure yet."""

    minutes: int
    opened: int
    resolved: int
    # Closed by the system after a verified recovery, as opposed to a human clicking Resolve.
    closed_by_verified_fix: int
    median_seconds_to_root_cause: float | None
    median_seconds_to_resolve: float | None
    rollbacks: int
