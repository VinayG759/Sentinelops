from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """The agent's conclusion. Rejected unless it cites evidence."""

    hypothesis: str = Field(description="The most likely root cause, in one or two sentences")
    confidence: Literal["low", "medium", "high"]
    evidence: list[int] = Field(min_length=1, description="evidence_id values that prove this")
    ruled_out: list[str] = Field(
        default_factory=list, description="Alternatives considered and why they were rejected"
    )
    suggested_fix: str = Field(
        default="", description="What a human should do. Not executed by anything yet."
    )


SUBMIT_TOOL = {
    "name": "submit_finding",
    "description": (
        "Report your conclusion and end the investigation. Every claim must be backed by "
        "evidence_id values returned by earlier tool calls."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "evidence": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "evidence_id values supporting the hypothesis (at least one)",
            },
            "ruled_out": {"type": "array", "items": {"type": "string"}},
            "suggested_fix": {"type": "string"},
        },
        "required": ["hypothesis", "confidence", "evidence"],
    },
}
