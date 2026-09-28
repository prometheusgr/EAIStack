"""Graph-building primitives for the workflow engine.

Each primitive is a small, independently unit-tested function that builds
one piece of a LangGraph StateGraph — a node, a conditional-edge router, or
(for review_loop, which needs two nodes plus a conditional edge wired
together) a small cluster of graph elements attached directly to a
StateGraph the caller owns. This mirrors chat_agent.py's own shape
(call_agent + route_after_agent) generalized to be reusable across
multiple named steps in one graph, rather than hardcoded to a single
"call_agent"/"call_tool" pair.

No class hierarchy: a primitive is a plain function that returns a plain
function (a node or a router), per AGENTS.md's composition-over-
inheritance and no-premature-abstraction guidance. app.workflows.compiler
is the only caller that assembles primitives into a full graph from a
validated WorkflowDef; these functions know nothing about YAML.
"""

from typing import Annotated, Any, Callable, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.mcp_client import Source


class WorkflowState(TypedDict):
    """Shared state for any graph the workflow engine compiles.

    Generalizes chat_agent.ChatState (messages/thread_id/user_id) with one
    addition: step_outputs, a dict keyed by step name holding each agent
    step's raw text response. This is the first workflow-engine graph to
    have more than one LLM-calling node, so route/review_loop need
    somewhere to read a specific step's latest output without re-scanning
    the full message list (which, per chat_agent.extract_sources_from_messages's
    documented gotcha, accumulates the *entire* checkpointed thread history,
    not just the current turn) or misinterpreting an intermediate step's
    output as a final chat reply.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    user_id: str
    step_outputs: dict[str, str]


NodeFn = Callable[[WorkflowState], dict[str, Any]]
RouterFn = Callable[[WorkflowState], str]

# StateGraph is generic over (state, context, input, output) schemas; every
# graph this engine builds shares the one WorkflowState schema with no
# separate context/input/output schema, so this alias is the concrete type
# every primitive/compiler function taking a `graph` parameter annotates
# with — spelling the bare four-parameter generic out at every call site
# would be pure repetition.
WorkflowStateGraph = StateGraph[WorkflowState, Any, Any, Any]


def build_agent_node(
    *,
    llm: BaseChatModel,
    system_prompt: str = "",
    step_name: str | None = None,
) -> NodeFn:
    """Build one LLM-calling node — the workflow-engine generalization of
    chat_agent.create_chat_agent's call_agent closure.

    step_name, when given, also records the response's raw text under
    state["step_outputs"][step_name], so a route or review_loop primitive
    downstream can read this step's decision directly. Omitted for a
    terminal/single-step workflow (e.g. today's one-step chat.yaml) that
    has no downstream primitive needing to inspect it.
    """

    def call_agent(state: WorkflowState) -> dict[str, Any]:
        messages: list[AnyMessage] = list(state["messages"])
        if system_prompt:
            messages = [SystemMessage(content=system_prompt), *messages]
        response = llm.invoke(messages)

        update: dict[str, Any] = {"messages": [response]}
        if step_name is not None:
            update["step_outputs"] = {**state.get("step_outputs", {}), step_name: response.content}
        return update

    return call_agent


def build_tool_node(tools: list[BaseTool]) -> ToolNode:
    """Wrap LangGraph's own ToolNode — the workflow engine doesn't need a
    custom tool-calling node, only a documented, discoverable place to
    build one alongside the other primitives (chat_agent.py currently
    constructs ToolNode(tools) inline; the compiler does the same thing
    through this function instead of duplicating that call site).
    """
    return ToolNode(tools)


def build_agent_tool_router(*, max_tool_call_rounds: int) -> RouterFn:
    """Route an agent step to its bound tool node while it keeps making
    tool calls, up to max_tool_call_rounds — the same two-way conditional
    edge chat_agent.route_after_agent implements today, extracted so any
    tool-bound agent step in a YAML-defined workflow can reuse it, not
    just the built-in chat workflow.
    """

    def route(state: WorkflowState) -> str:
        last_message = state["messages"][-1]
        has_tool_calls = isinstance(last_message, AIMessage) and bool(last_message.tool_calls)
        if not has_tool_calls:
            return END

        tool_call_rounds = sum(
            1
            for message in state["messages"]
            if isinstance(message, AIMessage) and message.tool_calls
        )
        if tool_call_rounds >= max_tool_call_rounds:
            return END
        return "__tool__"

    return route


def build_route_node(*, step_name: str, branches: list[str]) -> RouterFn:
    """Build a conditional-edge router that dispatches on a named step's
    recorded output (state["step_outputs"][step_name]) to whichever
    declared branch name that output contains.

    Generalizes chat_agent.route_after_agent's two-way branch (tool call
    vs. not) to N named branches driven by an upstream classifier agent's
    text response, per the `route` primitive in issue #81/#80's design.

    A response that matches none of the declared branches falls back to
    the first one rather than raising: the classifier is an LLM call, and
    per AGENTS.md's "error handling only at system boundaries," a
    malformed/unexpected model response at this boundary must degrade
    predictably, not crash the graph mid-turn.
    """
    if not branches:
        raise ValueError("route requires at least one branch")

    def route(state: WorkflowState) -> str:
        output = state.get("step_outputs", {}).get(step_name, "")
        for branch in branches:
            if branch in output:
                return branch
        return branches[0]

    return route


def build_review_loop(
    graph: WorkflowStateGraph,
    *,
    worker_step: str,
    reviewer_step: str,
    worker_node: NodeFn,
    reviewer_node: NodeFn,
    approve_keyword: str,
    max_iterations: int,
) -> None:
    """Attach the evaluator-optimizer pattern to graph: worker produces a
    draft, reviewer either approves (graph ends) or rejects (worker runs
    again), bounded by max_iterations rounds regardless of whether the
    reviewer ever approves.

    Unlike build_agent_tool_router's round counting (which scans the full
    message list for AIMessages with tool_calls — a signal that only ever
    means "the chat agent wants to call a tool"), this loop counts its own
    rounds from step_outputs, since a review_loop step must not be
    confused with an unrelated tool-call loop elsewhere in the same graph,
    and step_outputs already isolates one step's history by name.

    max_iterations must already be validated (by app.workflows.schema)
    against REVIEW_LOOP_MAX_ITERATIONS_CEILING before this function is
    called — this primitive enforces whatever bound it's given, it does
    not know about the ceiling itself.
    """
    if max_iterations < 1:
        raise ValueError("review_loop requires max_iterations >= 1")

    def reviewer_with_round_count(state: WorkflowState) -> dict[str, Any]:
        update = reviewer_node(state)
        rounds_so_far = state.get("step_outputs", {}).get(f"__{reviewer_step}_rounds", "0")
        update.setdefault("step_outputs", {})
        update["step_outputs"] = {
            **state.get("step_outputs", {}),
            **update["step_outputs"],
            f"__{reviewer_step}_rounds": str(int(rounds_so_far) + 1),
        }
        return update

    def route_after_review(state: WorkflowState) -> str:
        review_text = state.get("step_outputs", {}).get(reviewer_step, "")
        rounds_completed = int(state.get("step_outputs", {}).get(f"__{reviewer_step}_rounds", "0"))
        if approve_keyword in review_text:
            return END
        if rounds_completed >= max_iterations:
            return END
        return worker_step

    # LangGraph's add_node overloads unify a node's parameter type against
    # NodeInputT strictly enough that a callable returning a *partial*
    # state update (dict[str, Any], the standard LangGraph node shape used
    # throughout this module) rather than the full WorkflowState doesn't
    # resolve to any overload -- a known friction point in langgraph's
    # stubs for this common pattern, not a real type error: every node
    # here is exercised end-to-end by tests/unit/test_workflow_primitives.py
    # and tests/unit/test_workflow_compiler.py.
    graph.add_node(worker_step, worker_node)  # type: ignore[call-overload]
    graph.add_node(reviewer_step, reviewer_with_round_count)  # type: ignore[call-overload]
    graph.add_edge(worker_step, reviewer_step)
    graph.add_conditional_edges(
        reviewer_step,
        route_after_review,
        {worker_step: worker_step, END: END},
    )


def extract_sources_from_messages(messages: list[AnyMessage]) -> list[Source]:
    """Collect the current turn's search_knowledge_base sources (see
    app.mcp_client.doc_search_client's response_format=
    "content_and_artifact") into one flat, deduplicated list.

    Moved here from the deleted app.agents.chat_agent unchanged (issue
    #81 re-expresses chat as a YAML workflow, but this message-processing
    logic is generic across any workflow with a tool-bound agent step, not
    specific to chat) — see git history for chat_agent.py's original
    version if the full derivation is needed.

    messages is the full result["messages"] from a graph invocation, which
    -- per LangGraph's add_messages reducer and the SqlAlchemyCheckpointSaver
    -- is the *entire accumulated thread history*, not just this turn's new
    messages (see test_conversation_persists_across_two_invokes_same_thread_
    same_user in tests/unit/test_chat_workflow.py, which pins exactly this
    behavior). Scanning the whole list would both resurface a document that
    grounded a *previous* turn's unrelated answer, and crash outright on any
    ToolMessage restored from a checkpoint: SqlAlchemyCheckpointSaver
    round-trips messages through langgraph's JsonPlusSerializer, which
    deserializes ToolMessage.artifact as a plain dict, not a Source instance
    (Source has no custom serializer registered) -- so `source.
    knowledge_base_id` on a prior turn's artifact raises AttributeError.

    Restricting to messages after the last HumanMessage sidesteps both
    problems at once: within a single ainvoke() call, everything from the
    new HumanMessage onward (the turn currently being answered) is
    constructed fresh in this call and never round-tripped through the
    checkpointer, so its ToolMessage.artifact values are still real Source
    dataclass instances.
    """
    last_human_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_human_index = index
    current_turn_messages = messages[last_human_index + 1 :]

    sources: list[Source] = []
    seen_ids: set[str] = set()
    for message in current_turn_messages:
        if not isinstance(message, ToolMessage) or not message.artifact:
            continue
        for source in message.artifact:
            if source.knowledge_base_id in seen_ids:
                continue
            seen_ids.add(source.knowledge_base_id)
            sources.append(source)
    return sources
