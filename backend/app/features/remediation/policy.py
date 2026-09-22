"""How risky is this change, and how many humans must approve it?

Plain rules, no AI, no I/O — so it is fully unit-testable and cannot surprise anyone.
Fails closed: an unknown action or risk level is rejected rather than guessed.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from app.features.remediation.actions import Action, NotAllowed, Risk

APPROVALS_BY_RISK: dict[Risk, int] = {"low": 1, "medium": 1, "high": 2}

# Blast radius past this many services counts as wide enough to need a second approver.
WIDE_BLAST_RADIUS = 3


@dataclass(frozen=True)
class Decision:
    risk: Risk
    approvals_required: int
    reasons: list[str]


def decide(action: Action, params: BaseModel) -> Decision:
    risk = action.risk(params)
    if risk not in APPROVALS_BY_RISK:
        raise NotAllowed(f"Unknown risk level '{risk}' for action '{action.name}'")

    affected = action.affected_services(params)
    approvals = APPROVALS_BY_RISK[risk]
    reasons = [f"{action.name} is classed {risk} risk → {approvals} approval(s)"]

    if len(affected) >= WIDE_BLAST_RADIUS and approvals < 2:
        approvals = 2
        reasons.append(f"affects {len(affected)} services → a second approver is required")

    return Decision(risk=risk, approvals_required=approvals, reasons=reasons)
