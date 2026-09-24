"""Every catalog action names the one thing it changes; proposals merge on it."""

from app.features.remediation import actions


def _target(name: str, params: dict) -> str:
    action, parsed = actions.validate(name, params)
    return action.target(parsed)


def test_every_catalog_action_declares_a_target():
    for action in actions.CATALOG.values():
        assert "target" in type(action).__dict__, f"{action.name} must implement target()"


def test_different_values_for_the_same_setting_share_a_target():
    """The 24 Sep bug: one outage produced max_connections=50 and =100 as two proposals."""
    fifty = _target("set_database_max_connections", {"value": 50})
    hundred = _target("set_database_max_connections", {"value": 100})
    assert fifty == hundred == "postgres/max_connections"


def test_different_services_are_different_targets():
    assert _target("restart_service", {"service": "order-service"}) != _target(
        "restart_service", {"service": "payment-service"}
    )
