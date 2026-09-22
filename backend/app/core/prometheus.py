"""Minimal PromQL client (instant queries)."""

import math

import httpx

from app.core.config import get_settings


async def query(expr: str) -> list[tuple[dict[str, str], float]]:
    """Run an instant query. Returns (labels, value) pairs; NaN values are kept as NaN."""
    async with httpx.AsyncClient(timeout=5) as http:
        resp = await http.get(
            f"{get_settings().prometheus_url}/api/v1/query", params={"query": expr}
        )
        resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {body.get('error', body)}")
    return [(r["metric"], float(r["value"][1])) for r in body["data"]["result"]]


async def query_scalar(expr: str) -> float | None:
    """Single-value query. None when there is no series or the value is NaN (e.g. 0/0)."""
    results = await query(expr)
    if not results:
        return None
    value = results[0][1]
    return None if math.isnan(value) else value
