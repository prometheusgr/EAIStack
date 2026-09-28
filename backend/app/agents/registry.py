"""Name -> AgentDefinition lookup.

The first real implementation of the shape docs/AGENT_LIBRARY.md has
sketched since before any second agent existed. A plain dict, not a
dynamic loader — matching that doc's own "no premature abstraction"
stance: with today's agents all sourced from YAML workflow definitions
(app.workflows.loader), there is nothing to auto-discover beyond reading
that one directory once at startup.

Every entry's factory has the uniform signature (db: Session, token: str,
mcp_url: str) -> CompiledStateGraph — the same signature every hand-coded
agent in AGENT_LIBRARY.md's worked example uses, so app.api.agents (and
any future agent-facing endpoint) can resolve and invoke any registered
workflow identically regardless of whether it's hand-coded or
YAML-compiled.
"""

from dataclasses import dataclass
from typing import Any, Callable

from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.workflows.compiler import compile_workflow
from app.workflows.schema import WorkflowDef

AgentFactory = Callable[[Session, str, str], CompiledStateGraph[Any, Any, Any, Any]]


@dataclass(frozen=True)
class AgentDefinition:
    """One registered agent/workflow: its stable name (used for registry
    lookup, logging, and — in a later slice — audit/version tracking, not
    the source filename), the factory that builds it fresh per request,
    and its entry step's system prompt text (see
    WorkflowDef.entry_prompt) — the single source of truth app.api.agents
    needs for the output guardrail's leak detector, so that check compares
    against the exact text actually given to the model rather than a
    second, potentially-drifted copy.
    """

    name: str
    factory: AgentFactory
    system_prompt: str


_REGISTRY: dict[str, AgentDefinition] = {}


def get_agent_definition(name: str) -> AgentDefinition:
    """Look up a registered agent/workflow by its stable name.

    Raises KeyError (not None) for an unknown name: every call site today
    resolves a name the caller controls (e.g. the hardcoded "chat" in
    app.api.agents), so an unknown name is a startup/config bug, not a
    request-time condition to handle gracefully.
    """
    return _REGISTRY[name]


def register_workflow_definitions(definitions: dict[str, WorkflowDef]) -> None:
    """Register every loaded, validated workflow definition under the
    registry, replacing any existing entry with the same name.

    Each factory closes over its own WorkflowDef and calls
    compile_workflow fresh on every invocation — never caching a compiled
    graph across requests: a compiled graph's tools and checkpointer are
    bound to one caller's validated token and one request's db session,
    and reusing one across requests would leak that binding into an
    unrelated caller's turn.
    """
    for name, definition in definitions.items():
        _REGISTRY[name] = AgentDefinition(
            name=name,
            factory=_make_factory(definition),
            system_prompt=definition.entry_prompt(),
        )


def _make_factory(definition: WorkflowDef) -> AgentFactory:
    """Build one workflow definition's factory as its own named function,
    rather than a lambda closing over the register_workflow_definitions
    loop variable directly -- the classic late-binding closure bug (every
    lambda in the loop would otherwise see whatever `definition` the loop
    variable holds by the time it's *called*, not defined) plus a shape
    mypy can actually infer the parameter types for.
    """

    def factory(db: Session, token: str, mcp_url: str) -> CompiledStateGraph[Any, Any, Any, Any]:
        return compile_workflow(definition, db=db, token=token, mcp_url=mcp_url)

    return factory
