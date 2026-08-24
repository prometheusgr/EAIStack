"""Tests for the agent registry: the scaffolding a second agent plugs into
alongside chat_agent.

This does not test chat_agent's own behavior (see test_chat_agent.py) --
it tests that the registry pattern itself works, using a minimal fake
agent definition so the test doesn't depend on chat_agent's real graph.
"""

import pytest

from app.agents.registry import AgentDefinition, get_agent_definition, list_agent_names


@pytest.mark.unit
def test_chat_agent_is_registered():
    """The existing chat agent is registered under a stable, known name --
    the registry describes agents that already exist, not just future ones.
    """
    assert "chat" in list_agent_names()


@pytest.mark.unit
def test_get_agent_definition_returns_registered_definition():
    """Looking up a registered name returns its AgentDefinition."""
    definition = get_agent_definition("chat")

    assert isinstance(definition, AgentDefinition)
    assert definition.name == "chat"
    assert callable(definition.factory)


@pytest.mark.unit
def test_get_agent_definition_raises_for_unknown_name():
    """An unregistered name is a caller error, not a silent None -- the
    caller (an API endpoint) should fail loudly rather than proceed with
    a missing agent.
    """
    with pytest.raises(KeyError):
        get_agent_definition("does-not-exist")
