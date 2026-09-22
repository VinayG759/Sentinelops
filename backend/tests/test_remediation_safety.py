"""The guarantees that let an AI touch production: catalog, allow-list, policy.

If any of these fail, the executor must not be allowed near the cluster.
"""

import pytest
from pydantic import ValidationError

from app.features.remediation import actions, policy


def validated(name: str, params: dict):
    action, parsed = actions.validate(name, params)
    return action, parsed


# ── The catalog is the only vocabulary ───────────────────────────────────────

def test_unknown_action_is_refused():
    with pytest.raises(actions.NotAllowed, match="Unknown action"):
        actions.validate("rm_minus_rf", {})


@pytest.mark.parametrize("shell_ish", ["kubectl delete pods --all", "restart_service; drop db", ""])
def test_command_like_strings_are_not_actions(shell_ish):
    """The agent cannot smuggle a command: anything not in the catalog is rejected."""
    with pytest.raises(actions.NotAllowed):
        actions.validate(shell_ish, {})


# ── Targets outside the allow-list ───────────────────────────────────────────

@pytest.mark.parametrize("service", ["postgres", "prometheus", "kube-apiserver", "order-service-x"])
def test_restart_is_refused_for_services_outside_the_allow_list(service):
    with pytest.raises(actions.NotAllowed, match="not in the allow-list"):
        actions.validate("restart_service", {"service": service})


def test_service_port_change_is_limited_to_postgres():
    with pytest.raises(actions.NotAllowed):
        actions.validate("set_service_port", {"network_service": "kubernetes", "port": 443})


# ── Parameter ranges ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("replicas", [0, -1, 6, 500])
def test_replica_counts_outside_1_to_5_are_refused(replicas):
    with pytest.raises(ValidationError):
        actions.validate("scale_service", {"service": "order-service", "replicas": replicas})


@pytest.mark.parametrize("value", [0, 5, 19, 201, 100000])
def test_connection_limits_outside_20_to_200_are_refused(value):
    with pytest.raises(ValidationError):
        actions.validate("set_database_max_connections", {"value": value})


def test_missing_parameters_are_refused():
    with pytest.raises(ValidationError):
        actions.validate("scale_service", {"service": "order-service"})


# ── Policy ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("name", "params", "expected_risk", "expected_approvals"),
    [
        ("restart_service", {"service": "order-service"}, "low", 1),
        ("scale_service", {"service": "payment-service", "replicas": 3}, "low", 1),
        # touches shared networking for both services -> wide blast radius
        ("set_service_port", {"network_service": "postgres", "port": 5432}, "medium", 1),
        # restarts the shared database, and affects 3 services
        ("set_database_max_connections", {"value": 100}, "high", 2),
    ],
)
def test_policy_assigns_risk_and_approvals(name, params, expected_risk, expected_approvals):
    action, parsed = validated(name, params)
    decision = policy.decide(action, parsed)
    assert decision.risk == expected_risk
    assert decision.approvals_required == expected_approvals
    assert decision.reasons


def test_policy_fails_closed_on_an_unknown_risk_level():
    # A fresh instance, never the shared catalog one: patching that would leak between tests.
    action = actions.RestartService()
    action.risk = lambda params: "cosmic"  # a future action returning something unexpected
    parsed = action.Params(service="order-service")
    with pytest.raises(actions.NotAllowed, match="Unknown risk"):
        policy.decide(action, parsed)


def test_wide_blast_radius_forces_a_second_approver():
    action = actions.RestartService()
    action.affected_services = lambda params: ["a", "b", "c", "d"]
    parsed = action.Params(service="order-service")
    assert policy.decide(action, parsed).approvals_required == 2


# ── Every action must be undoable and checkable ──────────────────────────────

@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("restart_service", {"service": "order-service"}),
        ("scale_service", {"service": "order-service", "replicas": 2}),
        ("set_service_port", {"network_service": "postgres", "port": 5432}),
        ("set_database_max_connections", {"value": 100}),
    ],
)
def test_each_action_declares_a_rollback_and_a_verify_query(name, params):
    action, parsed = validated(name, params)
    assert action.rollback_plan(parsed)
    query = action.verify_query(parsed)
    assert "rate(" in query or query == "vector(1)"
    assert action.affected_services(parsed)
