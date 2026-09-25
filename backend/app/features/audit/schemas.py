from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ChainStatus(BaseModel):
    """The result of walking the whole hash chain, newest verification wins."""

    valid: bool
    # How many events were read before the walk stopped — the total when valid.
    checked: int
    # The first event whose stored hash does not match its contents, or whose
    # prev_hash does not match the event before it. None when the chain is intact.
    first_broken_id: int | None
    # Disclosed sequencing faults (migration 0002): their contents are still verified, only
    # their link is skipped. Always shown on the audit page, never hidden.
    known_exceptions: list[int] = []
    verified_at: datetime
    took_ms: int


class AuditEvent(BaseModel):
    id: int
    incident_id: UUID | None
    type: str
    actor: str
    payload: dict[str, Any]
    created_at: datetime
    prev_hash: str
    hash: str
