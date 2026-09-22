"""Background loop: every 15s, check each service's error ratio and open incidents."""

import asyncio
import logging

from app.core import events, prometheus
from app.core.db import get_pool
from app.features.incidents import rules, service

log = logging.getLogger(__name__)

TICK_SECONDS = 15
# Rate window. Must cover several 5s scrapes, but stay short: errors linger in the window
# after recovery, and a long window made freshly resolved incidents bounce straight back.
WINDOW = "30s"

_tracker = rules.BreachTracker()


def error_ratio_query(prefix: str) -> str:
    return (
        f"sum(rate({prefix}_errors_total[{WINDOW}])) / "
        f"sum(rate({prefix}_requests_total[{WINDOW}]))"
    )


def request_rate_query(prefix: str) -> str:
    return f"sum(rate({prefix}_requests_total[{WINDOW}]))"


@events.on("incident.resolved")
async def _restart_streak(event: events.Event) -> None:
    """After a resolution, require fresh consecutive breaches before reopening.

    By the second post-resolution check the window holds only post-resolution data,
    so a genuinely fixed service stays closed and a still-broken one reopens ~30s later.
    """
    incident = await service.get_incident(event["incident_id"])
    if incident:
        _tracker.reset(incident["service"])


async def _monitored_services() -> list[dict]:
    async with get_pool().connection() as conn:
        cur = await conn.execute(
            "select name, metric_prefix from public.services where metric_prefix is not null"
        )
        return await cur.fetchall()


async def check_once(tracker: rules.BreachTracker) -> None:
    for svc in await _monitored_services():
        name, prefix = svc["name"], svc["metric_prefix"]
        ratio_expr = error_ratio_query(prefix)
        ratio, rate = await asyncio.gather(
            prometheus.query_scalar(ratio_expr),
            prometheus.query_scalar(request_rate_query(prefix)),
        )
        breaching = tracker.observe(name, ratio, rate)
        log.info(
            "detector.tick",
            extra={"service": name, "error_ratio": ratio, "request_rate": rate,
                   "streak": tracker.streaks[name]},
        )
        if not breaching:
            continue
        incident = await service.open_incident(
            service=name,
            signal="error_rate",
            severity=rules.severity_for(ratio),
            title=f"{name}: {ratio:.0%} of requests failing",
            evidence={
                "error_ratio": round(ratio, 4),
                "request_rate": round(rate, 2),
                "threshold": rules.ERROR_RATIO_THRESHOLD,
                "promql": ratio_expr,
            },
        )
        if incident:
            log.warning("incident.opened", extra={"incident_id": str(incident["id"]),
                                                   "service": name})


async def run() -> None:
    log.info("detector started", extra={"tick_seconds": TICK_SECONDS, "window": WINDOW})
    while True:
        try:
            await check_once(_tracker)
        except Exception:
            # One bad tick (Prometheus restarting, network blip) must not kill detection.
            log.exception("detector tick failed")
        await asyncio.sleep(TICK_SECONDS)
