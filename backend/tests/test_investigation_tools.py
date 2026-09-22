"""Tool wiring: schemas match the functions, and guardrails hold."""

import pytest

from app.features.investigation import tools
from app.features.investigation.schemas import SUBMIT_TOOL, Finding


def test_every_tool_has_a_schema_and_vice_versa():
    assert {s["name"] for s in tools.TOOL_SCHEMAS} == set(tools.TOOLS)


def test_schemas_describe_real_arguments():
    import inspect

    for schema in tools.TOOL_SCHEMAS:
        params = inspect.signature(tools.TOOLS[schema["name"]]).parameters
        assert set(schema["input_schema"]["properties"]) <= set(params), schema["name"]
        assert set(schema["input_schema"]["required"]) <= set(params), schema["name"]
        assert schema["description"], schema["name"]


def test_submit_finding_schema_matches_the_validated_model():
    assert set(SUBMIT_TOOL["input_schema"]["properties"]) == set(Finding.model_fields)


async def test_unknown_tool_is_refused():
    with pytest.raises(ValueError, match="Unknown tool"):
        await tools.run_tool("delete_everything", {})


async def test_connectivity_probe_rejects_ports_outside_the_allow_list():
    with pytest.raises(ValueError, match="not allowed"):
        await tools.check_connectivity("order-service", "postgres", 22)


def test_no_tool_can_write_to_the_cluster():
    """Read-only by construction: guard against a write slipping into the toolset."""
    import inspect

    forbidden = ("patch_", "delete_", "create_namespaced", "replace_", "rollout_restart")
    for name, fn in tools.TOOLS.items():
        source = inspect.getsource(fn)
        assert not any(bad in source for bad in forbidden), f"{name} may modify the cluster"
