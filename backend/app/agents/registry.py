"""Registry of available agents: the pattern a second agent follows to sit
alongside chat_agent.

Only chat_agent is registered today -- this ticket is scaffolding, not a
second real agent. A new agent should:
  1. Live in its own module under app/agents/ (e.g. app/agents/summarizer_agent.py),
     following chat_agent.py's shape: a TypedDict state, a factory function
     that takes (db: Session, token: str, mcp_url: str) and returns a
     compiled graph built with SqlAlchemyCheckpointSaver(db).
  2. Keep its prompts in their own module under app/prompts/ (e.g.
     app/prompts/summarizer_prompts.py), as PromptTemplate instances --
     see app/prompts/chat_prompts.py.
  3. Register an AgentDefinition below with a stable `name` used as the
     registry key (and, if exposed over HTTP, the API path segment).

A single dict rather than a plugin/auto-discovery system: with exactly one
real agent, there is nothing to discover yet, and a dynamic loader would be
undocumented machinery serving a hypothetical third agent nobody has asked
for (see AGENTS.md's "No premature abstraction").
"""

from dataclasses import dataclass
from typing import Callable

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agents.chat_agent import create_chat_agent

AgentFactory = Callable[[Session, str, str], CompiledStateGraph]


@dataclass(frozen=True)
class AgentDefinition:
    """One entry in the agent registry.

    name is the stable identifier other code (API routing, logging,
    audit entries) should use to refer to this agent -- never the Python
    module or function name, which are free to change independently.
    """

    name: str
    factory: AgentFactory


_REGISTRY: dict[str, AgentDefinition] = {
    "chat": AgentDefinition(name="chat", factory=create_chat_agent),
}


def list_agent_names() -> list[str]:
    """Return every registered agent's name."""
    return list(_REGISTRY.keys())


def get_agent_definition(name: str) -> AgentDefinition:
    """Look up a registered agent by name.

    Raises KeyError for an unregistered name rather than returning None:
    a caller asking for a specific agent by name has already decided it
    must exist, so a missing entry is a bug to surface loudly, not a case
    to handle gracefully.
    """
    return _REGISTRY[name]
