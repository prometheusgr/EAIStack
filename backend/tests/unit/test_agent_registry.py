"""Tests for app.agents.registry: name -> AgentDefinition lookup.

The first real implementation of the shape docs/AGENT_LIBRARY.md has
described since before any second agent existed — see that doc's own
registry.py sketch, which this module now makes real.
"""

import pytest

from app.agents.registry import (
    AgentDefinition,
    get_agent_definition,
    register_workflow_definitions,
)
from app.core.llm_client import FakeChatModel
from app.workflows.schema import parse_workflow_definition

_UNUSED_TOKEN = "unused-token"
_UNREACHABLE_MCP_URL = "http://localhost:1/mcp"


def test_get_agent_definition_raises_for_unknown_name():
    with pytest.raises(KeyError):
        get_agent_definition("does-not-exist")


def test_register_workflow_definitions_makes_them_resolvable(db_session, monkeypatch):
    """A workflow loaded from YAML (app.workflows.loader) becomes callable
    through the registry's uniform (db, token, mcp_url) -> CompiledStateGraph
    factory signature — the same shape every hand-coded agent already
    uses (see docs/AGENT_LIBRARY.md).
    """
    monkeypatch.setattr(
        "app.workflows.compiler.get_llm_client", lambda db: FakeChatModel(response="hello!")
    )
    definition = parse_workflow_definition(
        {
            "name": "greeter",
            "version": 1,
            "entry": "respond",
            "steps": {"respond": {"type": "agent", "prompt": "Greet the user."}},
        },
        source_file="greeter.yaml",
    )

    register_workflow_definitions({"greeter": definition})

    agent_definition = get_agent_definition("greeter")
    assert isinstance(agent_definition, AgentDefinition)
    assert agent_definition.name == "greeter"
    assert agent_definition.system_prompt == "Greet the user."

    graph = agent_definition.factory(db_session, _UNUSED_TOKEN, _UNREACHABLE_MCP_URL)
    assert hasattr(graph, "invoke")


def test_register_workflow_definitions_leaves_system_prompt_none_for_a_route_entry():
    """A workflow whose entry step is `route` (or `review_loop`), not a
    single `agent` step, has no one "the" system prompt -- registration
    must not raise (WorkflowDef.entry_prompt would), and system_prompt
    must be None rather than a fabricated/wrong string (issue #82's
    triage.yaml is the first built-in workflow with this shape).
    """
    definition = parse_workflow_definition(
        {
            "name": "classifier_only",
            "version": 1,
            "entry": "classify",
            "steps": {
                "classify": {
                    "type": "route",
                    "prompt": "Classify as a or b.",
                    "branches": {"a": "a_agent", "b": "b_agent"},
                },
                "a_agent": {"type": "agent", "prompt": "Handle a."},
                "b_agent": {"type": "agent", "prompt": "Handle b."},
            },
        },
        source_file="classifier_only.yaml",
    )

    register_workflow_definitions({"classifier_only": definition})

    assert get_agent_definition("classifier_only").system_prompt is None
