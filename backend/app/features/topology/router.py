"""Live service health: what the system looks like right now.

Feeds the overview screen (and, later, the blast-radius map). All numbers come from
Prometheus and Kubernetes — nothing here is illustrative.
"""

import asyncio
import time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core import k8s, prometheus, service_metrics
from app.core.auth import User, current_user
from app.core.db import get_pool

router = APIRouter(prefix="/api/topology", tags=["topology"])

SPARK_POINTS = 30
DEGRADED_RATIO = 0.02
CRITICAL_RATIO = 0.20


class ServiceHealth(BaseModel):
    name: str
    kind: str
    status: str  # healthy | degraded | critical | unknown
    depends_on: list[str]
    error_ratio: float | None = None
    requests_per_second: float | None = None
    p95_latency_ms: float | None = None
    pods_ready: int | None = None
    pods_desired: int | None = None
    spark: list[float] = []


def _status(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio >= CRITICAL_RATIO:
        return "critical"
    if ratio >= DEGRADED_RATIO:
        return "degraded"
    return "healthy"


async def _pods(deployment: str) -> tuple[int | None, int | None]:
    def read() -> tuple[int | None, int | None]:
        dep = k8s.apps().read_namespaced_deployment(deployment, k8s.namespace())
        return dep.status.ready_replicas or 0, dep.spec.replicas

    try:
        return await asyncio.to_thread(read)
    except Exception:
        return None, None


async def _service_health(row: dict, minutes: int) -> ServiceHealth:
    prefix = row["metric_prefix"]
    ready, desired = await _pods(row["deployment"])
    base = ServiceHealth(
        name=row["name"], kind=row["kind"], status="unknown",
        depends_on=list(row["depends_on"] or []), pods_ready=ready, pods_desired=desired,
    )
    if not prefix:
        # Components without application metrics (the database) are judged by their pods.
        base.status = "healthy" if ready and desired and ready >= desired else "unknown"
        return base

    end = time.time()
    ratio_expr = service_metrics.error_ratio_expr(prefix)
    ratio, rate, p95, series = await asyncio.gather(
        prometheus.query_scalar(ratio_expr),
        prometheus.query_scalar(f"sum(rate({prefix}_requests_total[1m]))"),
        prometheus.query_scalar(
            f"histogram_quantile(0.95, sum(rate({prefix}_request_duration_ms_bucket[1m])) by (le))"
        ),
        prometheus.query_range(
            ratio_expr, end - minutes * 60, end, max(10, minutes * 60 // SPARK_POINTS)
        ),
    )
    base.error_ratio = ratio
    base.requests_per_second = rate
    base.p95_latency_ms = p95
    base.spark = [value for _, value in series]
    base.status = _status(ratio)
    return base


async def _services() -> list[dict]:
    async with get_pool().connection() as conn:
        return await (
            await conn.execute(
                "select name, kind, deployment, metric_prefix, depends_on "
                "from public.services order by kind, name"
            )
        ).fetchall()


@router.get("", response_model=list[ServiceHealth])
async def topology(
    minutes: int = Query(15, ge=5, le=360, description="Sparkline window"),
    _: User = Depends(current_user),
):
    rows = await _services()
    return await asyncio.gather(*(_service_health(row, minutes) for row in rows))


class ServiceMetrics(BaseModel):
    start: float
    end: float
    step: int
    # service name -> signal name -> [(unix_seconds, value)]
    services: dict[str, dict[str, list[tuple[float, float]]]]


@router.get("/metrics", response_model=ServiceMetrics)
async def all_service_metrics(
    minutes: int = Query(60, ge=5, le=360), _: User = Depends(current_user)
):
    """Golden signals for every service with application metrics, on one shared time axis."""
    rows = [row for row in await _services() if row["metric_prefix"]]
    end = time.time()
    start, step = end - minutes * 60, service_metrics.step_for(minutes)
    results = await asyncio.gather(
        *(service_metrics.series(row["metric_prefix"], start, end, step) for row in rows)
    )
    return ServiceMetrics(
        start=start, end=end, step=step,
        services={row["name"]: result for row, result in zip(rows, results, strict=True)},
    )
