"""Compile a validated WorkflowDef into a runnable, checkpointed LangGraph
StateGraph.

Built fresh per request: tools bind the caller's own already-validated
token, and the checkpointer binds this request's db session — neither
can be cached across requests without leaking one caller's
credentials/session into another's turn.
"""


from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.core.llm_client import get_llm_client
from app.workflows.primitives import (
    WorkflowState,
    WorkflowStateGraph,
    build_agent_node,
    build_agent_tool_router,
    build_review_loop,
    build_route_node,
    build_tool_node,
)
from app.workflows.schema import (
    AgentStepDef,
    ReviewLoopStepDef,
    RouteStepDef,
    WorkflowDef,
)
from app.workflows.tool_registry import get_tool_factory

# chat_agent.MAX_TOOL_CALL_ROUNDS's equivalent for any YAML-defined agent
# step that binds tools: a hard cap on how many tool-call round-trips one
# agent step can make per turn, independent of review_loop's own
# max_iterations ceiling (a different loop, a different risk -- runaway
# tool calls vs. runaway review cycles). Not YAML-configurable in this
# slice: no workflow definition has needed a different value yet, and
# chat.yaml (the only agent step with tools today) already relies on this
# exact number via chat_agent.MAX_TOOL_CALL_ROUNDS.
_MAX_TOOL_CALL_ROUNDS = 5


def compile_workflow(
    definition: WorkflowDef, *, db: Session, token: str, mcp_url: str
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Build and compile a StateGraph for one validated workflow
    definition, scoped to one request's caller/db session.
    """
    graph: WorkflowStateGraph = StateGraph(WorkflowState)

    # Maps each top-level YAML step name to the actual graph node that
    # represents its entry point. For agent/route steps these are the
    # same name; review_loop is the one primitive whose top-level step
    # name (e.g. "worker" in a YAML file) is a label for a whole
    # worker/reviewer pair, not itself a graph node -- its entry is
    # worker_step, the node build_review_loop actually attaches first.
    entry_nodes: dict[str, str] = {}

    for step_name, step in definition.steps.items():
        if isinstance(step, AgentStepDef):
            _attach_agent_step(graph, step_name, step, db=db, token=token, mcp_url=mcp_url)
            entry_nodes[step_name] = step_name
        elif isinstance(step, ReviewLoopStepDef):
            _attach_review_loop_step(graph, step, db=db)
            entry_nodes[step_name] = step.worker_step
        elif isinstance(step, RouteStepDef):
            _attach_route_step(graph, step_name, step, db=db)
            entry_nodes[step_name] = step_name

    graph.set_entry_point(entry_nodes[definition.entry])
    return graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db))


def _attach_agent_step(
    graph: WorkflowStateGraph,
    step_name: str,
    step: AgentStepDef,
    *,
    db: Session,
    token: str,
    mcp_url: str,
) -> None:
    """Attach one `agent` step, plus its tool node and routing if it binds
    any tools -- the same call_agent/ToolNode/route_after_agent triangle
    chat_agent.create_chat_agent wires by hand, generalized to a named
    step in a larger graph instead of the graph's only node.
    """
    tools = [_build_tool(name, token=token, mcp_url=mcp_url) for name in step.tools]
    llm = get_llm_client(db)
    if tools:
        llm = llm.bind_tools(tools)

    node = build_agent_node(llm=llm, system_prompt=step.prompt, step_name=step_name)
    # See the matching type: ignore comment in app.workflows.primitives.
    # build_review_loop for why LangGraph's add_node overloads don't
    # resolve for a partial-state-update node callable.
    graph.add_node(step_name, node)  # type: ignore[call-overload,arg-type]

    if not tools:
        _attach_default_edge(graph, step_name, step.next)
        return

    tool_node_name = f"{step_name}__tools"
    graph.add_node(tool_node_name, build_tool_node(tools))
    router = build_agent_tool_router(max_tool_call_rounds=_MAX_TOOL_CALL_ROUNDS)

    next_target = step.next if step.next else END
    graph.add_conditional_edges(
        step_name,
        router,
        {"__tool__": tool_node_name, END: next_target},
    )
    graph.add_edge(tool_node_name, step_name)


def _build_tool(name: str, *, token: str, mcp_url: str):
    """Resolve and build one YAML-referenced tool.

    The name-is-registered check already happened at schema validation
    time (app.workflows.schema._validate_definition, via
    app.workflows.tool_registry.is_registered_tool) -- this function
    should never actually see an unregistered name once a WorkflowDef has
    passed parse_workflow_definition. The assertion exists so a violated
    invariant fails loudly and specifically here, rather than as an
    opaque "NoneType is not callable" a few lines down.
    """
    factory = get_tool_factory(name)
    assert factory is not None, f"tool '{name}' is not registered (should have failed validation)"
    return factory(token, mcp_url)


def _attach_default_edge(graph: WorkflowStateGraph, step_name: str, next_step: str | None) -> None:
    graph.add_edge(step_name, next_step if next_step else END)


def _attach_review_loop_step(
    graph: WorkflowStateGraph, step: ReviewLoopStepDef, *, db: Session
) -> None:
    worker_llm = get_llm_client(db)
    reviewer_llm = get_llm_client(db)

    build_review_loop(
        graph,
        worker_step=step.worker_step,
        reviewer_step=step.reviewer_step,
        worker_node=build_agent_node(
            llm=worker_llm, system_prompt=step.worker_prompt, step_name=step.worker_step
        ),
        reviewer_node=build_agent_node(
            llm=reviewer_llm, system_prompt=step.reviewer_prompt, step_name=step.reviewer_step
        ),
        approve_keyword=step.approve_keyword,
        max_iterations=step.max_iterations,
    )


def _attach_route_step(
    graph: WorkflowStateGraph, step_name: str, step: RouteStepDef, *, db: Session
) -> None:
    llm = get_llm_client(db)
    node = build_agent_node(llm=llm, system_prompt=step.prompt, step_name=step_name)
    graph.add_node(step_name, node)  # type: ignore[call-overload,arg-type]

    branch_names = list(step.branches.keys())
    router = build_route_node(step_name=step_name, branches=branch_names)
    edge_map: dict[str, str] = {
        branch_name: step.branches[branch_name] for branch_name in branch_names
    }
    # dict[str, str] is a valid dict[Hashable, str] at runtime; mypy's
    # invariant dict typing just doesn't see str as a subtype of Hashable
    # here without an explicit cast.
    graph.add_conditional_edges(step_name, router, edge_map)  # type: ignore[arg-type]
