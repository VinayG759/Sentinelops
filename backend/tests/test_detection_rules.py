from app.features.incidents.rules import BreachTracker, severity_for

HIGH = 0.5  # error ratio well above threshold
RATE = 4.0  # healthy traffic, req/s


def test_below_threshold_never_breaches():
    t = BreachTracker()
    assert not any(t.observe("svc", 0.01, RATE) for _ in range(5))


def test_single_spike_is_not_an_incident():
    t = BreachTracker()
    assert t.observe("svc", HIGH, RATE) is False


def test_two_consecutive_breaches_open():
    t = BreachTracker()
    t.observe("svc", HIGH, RATE)
    assert t.observe("svc", HIGH, RATE) is True


def test_recovery_between_spikes_resets_streak():
    t = BreachTracker()
    t.observe("svc", HIGH, RATE)
    t.observe("svc", 0.0, RATE)
    assert t.observe("svc", HIGH, RATE) is False


def test_no_data_is_not_an_outage():
    """0 errors / 0 requests is NaN in PromQL, which the client turns into None."""
    t = BreachTracker()
    assert not any(t.observe("svc", None, None) for _ in range(5))


def test_too_little_traffic_is_not_judged():
    t = BreachTracker()
    assert not any(t.observe("svc", 1.0, 0.01) for _ in range(5))


def test_keeps_reporting_while_still_broken():
    """A manually resolved incident that is still broken gets reopened; dedup absorbs repeats."""
    t = BreachTracker()
    results = [t.observe("svc", HIGH, RATE) for _ in range(4)]
    assert results == [False, True, True, True]


def test_reset_requires_fresh_consecutive_breaches():
    """After a resolution, lingering errors in the window must not instantly reopen."""
    t = BreachTracker()
    t.observe("svc", HIGH, RATE)
    t.observe("svc", HIGH, RATE)
    t.reset("svc")
    assert t.observe("svc", HIGH, RATE) is False  # one stale breach is not enough
    assert t.observe("svc", 0.0, RATE) is False  # window now clean -> stays closed


def test_services_are_tracked_independently():
    t = BreachTracker()
    t.observe("a", HIGH, RATE)
    assert t.observe("b", HIGH, RATE) is False


def test_severity_bands():
    assert severity_for(1.0) == "sev1"
    assert severity_for(0.5) == "sev1"
    assert severity_for(0.3) == "sev2"
    assert severity_for(0.06) == "sev3"
