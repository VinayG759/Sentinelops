"""Detection rules — pure logic, no I/O, so every edge case is unit-testable."""

from dataclasses import dataclass, field

ERROR_RATIO_THRESHOLD = 0.05  # >5% of requests failing
CONSECUTIVE_TICKS = 2  # must breach on 2 checks in a row (filters one-off blips)
MIN_REQUEST_RATE = 0.1  # req/s; below this there is too little traffic to judge


def severity_for(error_ratio: float) -> str:
    if error_ratio >= 0.5:
        return "sev1"
    if error_ratio >= 0.2:
        return "sev2"
    return "sev3"


@dataclass
class BreachTracker:
    """Counts consecutive threshold breaches per service."""

    streaks: dict[str, int] = field(default_factory=dict)

    def observe(self, service: str, error_ratio: float | None, request_rate: float | None) -> bool:
        """Record one check. True when the service has breached for CONSECUTIVE_TICKS or more.

        No data or no traffic resets the streak: "0 errors out of 0 requests" is not an outage.
        Returning True on every tick past the threshold is deliberate — opening is deduplicated
        downstream, and it means an incident resolved while still broken gets reopened.
        """
        judgeable = (
            error_ratio is not None
            and request_rate is not None
            and request_rate >= MIN_REQUEST_RATE
        )
        if judgeable and error_ratio > ERROR_RATIO_THRESHOLD:
            self.streaks[service] = self.streaks.get(service, 0) + 1
        else:
            self.streaks[service] = 0
        return self.streaks[service] >= CONSECUTIVE_TICKS

    def reset(self, service: str) -> None:
        """Forget the current streak (e.g. after a human resolves the incident)."""
        self.streaks[service] = 0
