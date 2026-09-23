"""Per-service time series from Prometheus: error ratio, request rate, p95 latency.

Shared by the incident charts and the overview so every chart asks the same question the
same way. All numbers are live PromQL results; nothing here is illustrative.
"""

import asyncio

from app.core import prometheus

RATE_WINDOW = "1m"
POINTS = 120  # roughly how many points a chart gets, whatever the time range


def step_for(minutes: int) -> int:
    """Seconds between points: ~POINTS per chart, never finer than Prometheus' 10s-ish scrape."""
    return max(10, (minutes * 60) // POINTS)


def error_ratio_expr(prefix: str) -> str:
    return (
        f"sum(rate({prefix}_errors_total[{RATE_WINDOW}])) / "
        f"sum(rate({prefix}_requests_total[{RATE_WINDOW}]))"
    )


async def series(prefix: str, start: float, end: float, step: int) -> dict[str, list]:
    """The three golden signals for one service over [start, end]."""
    error_ratio, request_rate, p95 = await asyncio.gather(
        prometheus.query_range(error_ratio_expr(prefix), start, end, step),
        prometheus.query_range(
            f"sum(rate({prefix}_requests_total[{RATE_WINDOW}]))", start, end, step
        ),
        prometheus.query_range(
            f"histogram_quantile(0.95, sum(rate({prefix}_request_duration_ms_bucket"
            f"[{RATE_WINDOW}])) by (le))",
            start, end, step,
        ),
    )
    return {
        "error_ratio": error_ratio,
        "requests_per_second": request_rate,
        "p95_latency_ms": p95,
    }
