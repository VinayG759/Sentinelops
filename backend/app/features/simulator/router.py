import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import events
from app.core.auth import Role, User, current_user, require_role
from app.features.simulator.scenarios import SCENARIOS, Scenario

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


class ScenarioOut(BaseModel):
    name: str
    title: str
    description: str
    state: Literal["active", "inactive", "unknown"]


STATE_TIMEOUT_SECONDS = 6


async def _describe(s: Scenario) -> ScenarioOut:
    try:
        # Bounded: a missing cluster must not leave the page loading forever.
        active = await asyncio.wait_for(
            asyncio.to_thread(s.is_active), timeout=STATE_TIMEOUT_SECONDS
        )
        state = "active" if active else "inactive"
    except Exception:
        state = "unknown"  # cluster unreachable, or Postgres mid-restart
    return ScenarioOut(name=s.name, title=s.title, description=s.description, state=state)


@router.get("/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(_: User = Depends(current_user)):
    return await asyncio.gather(*(_describe(s) for s in SCENARIOS.values()))


@router.post("/scenarios/{name}/{op}", response_model=ScenarioOut)
async def run_scenario(
    name: str, op: Literal["inject", "reset"], user: User = Depends(require_role(Role.admin))
):
    scenario = SCENARIOS.get(name)
    if scenario is None:
        raise HTTPException(404, f"Unknown scenario '{name}'")
    await asyncio.to_thread(scenario.inject if op == "inject" else scenario.reset)
    await events.emit(f"simulator.{op}", f"user:{user.id}", {"scenario": name})
    return await _describe(scenario)
