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

from typing import Annotated, Any, Callable, Literal, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from app.mcp_client import Source


class ReviewResult(BaseModel):
    """Structured output a review_loop's reviewer step must return.

    Required by issue #82: local models' free-text critiques are unreliable
    and code can't branch on them, so the reviewer's verdict is
    grammar-constrained JSON (via with_structured_output), not prose a
    substring match is applied to (slice 1's illustrative-only
    approve_keyword scheme, now replaced).
    """

    approved: bool
    issues: list[str] = Field(default_factory=list)


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

    task/draft/review (issue #82's documented state-shape decision): a
    review_loop's intermediate worker drafts and reviewer verdicts are
    read/written here, never appended to `messages` -- app.api.agents.chat
    reads result["messages"][-1] as the reply shown to the user, so an
    unreviewed draft or a reviewer's structured critique landing in
    `messages` would leak into the visible transcript and pollute the
    worker's own next-round context with its own prior turns. Only the
    review loop's *final* approved-or-exhausted draft is appended to
    `messages`, once, when the loop ends. `task` is written by an upstream
    interpreter `agent` step (via build_agent_node's output_field param) so
    a review_loop's worker/reviewer prompts can reference the restated task
    without it appearing in `messages` either.

    draft_tool_exchange holds the current round's worker tool-call
    AIMessage/ToolMessage pair(s) (empty if the worker made no tool calls
    this round), overwritten -- not accumulated -- on every worker round;
    only the *final* round's exchange is ever appended to `messages`, by
    build_review_loop's finalize step, so extract_sources_from_messages can
    find the sources that grounded the answer the user actually sees,
    without every rejected draft's tool calls also leaking into the visible
    transcript.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    user_id: str
    step_outputs: dict[str, str]
    task: str
    draft: str
    review: Optional[ReviewResult]
    draft_tool_exchange: list[AnyMessage]


NodeFn = Callable[[WorkflowState], dict[str, Any]]
RouterFn = Callable[[WorkflowState], str]

# StateGraph is generic over (state, context, input, output) schemas; every
# graph this engine builds shares the one WorkflowState schema with no
# separate context/input/output schema, so this alias is the concrete type
# every primitive/compiler function taking a `graph` parameter annotates
# with — spelling the bare four-parameter generic out at every call site
# would be pure repetition.
WorkflowStateGraph = StateGraph[WorkflowState, Any, Any, Any]

# The review_loop worker's own tool-call round cap -- mirrors
# app.workflows.compiler._MAX_TOOL_CALL_ROUNDS's role for a plain agent
# step, but private to this module since a worker's tool calls are resolved
# internally within one worker_node invocation (see build_review_loop),
# never as separate graph nodes the compiler wires up itself.
_WORKER_MAX_TOOL_CALL_ROUNDS = 5


def build_agent_node(
    *,
    llm: BaseChatModel,
    system_prompt: str = "",
    step_name: str | None = None,
    output_field: Literal["task", "draft", "review"] | None = None,
) -> NodeFn:
    """Build one LLM-calling node — the workflow-engine generalization of
    chat_agent.create_chat_agent's call_agent closure.

    step_name, when given, also records the response's raw text under
    state["step_outputs"][step_name], so a route or review_loop primitive
    downstream can read this step's decision directly. Omitted for a
    terminal/single-step workflow (e.g. today's one-step chat.yaml) that
    has no downstream primitive needing to inspect it.

    output_field, when given, writes the response text to that named
    WorkflowState field (state["task"]/["draft"]/["review"]) *instead of*
    appending it to `messages` -- used by an interpreter step feeding a
    review_loop's `task`, per issue #82's state-shape decision (see
    WorkflowState's docstring). Default None preserves every existing
    behavior (chat.yaml, plain sequence/route steps): the response is
    appended to `messages` as before.
    """

    def call_agent(state: WorkflowState) -> dict[str, Any]:
        messages: list[AnyMessage] = list(state["messages"])
        if system_prompt:
            messages = [SystemMessage(content=system_prompt), *messages]
        response = llm.invoke(messages)

        update: dict[str, Any] = {} if output_field else {"messages": [response]}
        if output_field:
            update[output_field] = response.content
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


def _format_prompt(template: str, state: WorkflowState) -> str:
    """Render a review_loop worker/reviewer prompt's {task}/{draft}/
    {review_issues} placeholders from state, defaulting missing fields to
    "" so a prompt referencing only a subset of them (or none, or none yet
    populated on the loop's first round) never raises KeyError.

    Deliberately plain str.format() against this one small fixed set of
    fields, not a new templating engine or a change to the unrelated
    PromptTemplate (app.prompts.prompt_template, which has no substitution
    of its own and is documented as "add it when a concrete prompt needs
    it") -- these prompts are YAML-inline text assembled directly here, not
    routed through PromptTemplate.
    """
    review = state.get("review")
    review_issues = "; ".join(review.issues) if review and review.issues else ""
    return template.format(
        task=state.get("task", ""),
        draft=state.get("draft", ""),
        review_issues=review_issues,
    )


def build_review_loop(
    graph: WorkflowStateGraph,
    *,
    worker_step: str,
    reviewer_step: str,
    worker_llm: BaseChatModel,
    worker_prompt: str,
    worker_tools: list[BaseTool] | None = None,
    reviewer_llm: BaseChatModel,
    reviewer_prompt: str,
    max_iterations: int,
) -> None:
    """Attach the evaluator-optimizer pattern to graph: worker drafts,
    reviewer returns a structured ReviewResult that either approves (loop
    ends) or rejects (worker runs again), bounded by max_iterations rounds
    regardless of whether the reviewer ever approves.

    Per issue #82's state-shape decision (see WorkflowState's docstring):
    every intermediate worker draft and reviewer verdict is read/written
    via state["draft"]/state["review"], never appended to `messages`. Only
    once the loop ends does the *final* draft get appended to `messages`
    as a single AIMessage -- the one message a downstream step or the user
    ever sees from the whole loop.

    The reviewer's verdict is structured (ReviewResult), not prose matched
    against a keyword (slice 1's illustrative-only approve_keyword scheme):
    local models' free-text critiques are unreliable and code can't branch
    on them. reviewer_llm.with_structured_output(ReviewResult) is called
    once per round; a parse failure (malformed/non-conforming model output)
    is treated as an unapproved review with a synthetic issue, and still
    counts as one round against max_iterations -- an LLM response is never
    fully trustworthy at this system boundary (AGENTS.md's "error handling
    only at system boundaries"), and this loop must not hang forever
    because the reviewer never returned parseable JSON.

    Unlike build_agent_tool_router's round counting (which scans the full
    message list for AIMessages with tool_calls), this loop counts its own
    rounds from step_outputs, since a review_loop step must not be
    confused with an unrelated tool-call loop elsewhere in the same graph.

    max_iterations must already be validated (by app.workflows.schema)
    against REVIEW_LOOP_MAX_ITERATIONS_CEILING before this function is
    called — this primitive enforces whatever bound it's given, it does
    not know about the ceiling itself.
    """
    if max_iterations < 1:
        raise ValueError("review_loop requires max_iterations >= 1")

    bound_worker_llm = worker_llm.bind_tools(worker_tools) if worker_tools else worker_llm
    worker_tool_node = build_tool_node(worker_tools) if worker_tools else None

    async def worker_node(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        """Draft (or revise) an answer to the task, resolving any tool
        calls the worker makes internally before returning.

        Accepts config (LangGraph injects it automatically for a node
        function declaring this second parameter) and forwards it to
        worker_tool_node.ainvoke: ToolNode reads its runtime context (e.g.
        the enclosing graph's RunnableConfig) from there, and calling it
        without one -- as this internal, node-within-a-node invocation
        would otherwise do -- raises "Missing required config key".

        async, unlike every other node in this module: search_knowledge_base
        (app.mcp_client.doc_search_client.make_search_knowledge_base_tool)
        is declared coroutine-only (no sync func=), matching MCP's own
        async client -- ToolNode.invoke() cannot run a coroutine-only tool
        (confirmed: it raises NotImplementedError), so a worker step that
        binds worker_tools must drive both the LLM and the tool node via
        their async (ainvoke) path. This matches how the graph is actually
        invoked in production (app.api.agents.chat calls agent.ainvoke()),
        and LangGraph runs an async node's coroutine directly rather than
        requiring every node in a graph to share one sync/async style.

        Tool-call rounds are resolved as a private loop scoped to this one
        worker invocation, not as separate graph nodes/edges: a review_loop
        round is one worker-draft-then-reviewer-verdict cycle, and a tool
        call the worker makes while drafting is bookkeeping internal to
        producing that one draft, not a review_loop round of its own (the
        same separation build_agent_tool_router's own round counting keeps
        from an unrelated tool-call loop elsewhere in the graph).

        The tool exchange itself (AIMessage with tool_calls + the
        resulting ToolMessages) is kept out of state["messages"] for every
        rejected draft, same as the draft text itself -- but this round's
        tool messages are recorded under step_outputs so finalize_draft can
        re-attach the *final* round's exchange once the loop ends, letting
        extract_sources_from_messages (app.workflows.primitives) find the
        search_knowledge_base sources that actually grounded the answer the
        user sees, exactly as it already does for a plain tool-bound agent
        step.
        """
        prompt = _format_prompt(worker_prompt, state)
        conversation: list[AnyMessage] = [SystemMessage(content=prompt), *state["messages"]]

        response: AnyMessage = await bound_worker_llm.ainvoke(conversation)
        tool_exchange: list[AnyMessage] = []
        tool_rounds = 0
        while (
            worker_tool_node is not None
            and isinstance(response, AIMessage)
            and response.tool_calls
            and tool_rounds < _WORKER_MAX_TOOL_CALL_ROUNDS
        ):
            conversation.append(response)
            tool_exchange.append(response)
            tool_result = await worker_tool_node.ainvoke({"messages": conversation}, config)
            conversation.extend(tool_result["messages"])
            tool_exchange.extend(tool_result["messages"])
            response = await bound_worker_llm.ainvoke(conversation)
            tool_rounds += 1

        draft_text = response.content
        return {
            "draft": draft_text,
            "draft_tool_exchange": tool_exchange,
            "step_outputs": {**state.get("step_outputs", {}), worker_step: draft_text},
        }

    structured_reviewer = reviewer_llm.with_structured_output(ReviewResult)

    def reviewer_node(state: WorkflowState) -> dict[str, Any]:
        prompt = _format_prompt(reviewer_prompt, state)
        try:
            review = structured_reviewer.invoke([SystemMessage(content=prompt)])
            if not isinstance(review, ReviewResult):
                review = ReviewResult.model_validate(review)
        except Exception:
            review = ReviewResult(approved=False, issues=["reviewer output could not be parsed"])

        rounds_so_far = state.get("step_outputs", {}).get(f"__{reviewer_step}_rounds", "0")
        return {
            "review": review,
            "step_outputs": {
                **state.get("step_outputs", {}),
                reviewer_step: review.model_dump_json(),
                f"__{reviewer_step}_rounds": str(int(rounds_so_far) + 1),
            },
        }

    def finalize_draft(state: WorkflowState) -> dict[str, Any]:
        """Append the loop's final draft to `messages`, plus the tool
        exchange (if any) that grounded that specific draft -- together,
        the only messages the whole loop ever contributes to the visible
        transcript and to extract_sources_from_messages.
        """
        tool_exchange = state.get("draft_tool_exchange") or []
        return {"messages": [*tool_exchange, AIMessage(content=state.get("draft", ""))]}

    def route_after_review(state: WorkflowState) -> str:
        review = state.get("review")
        rounds_completed = int(state.get("step_outputs", {}).get(f"__{reviewer_step}_rounds", "0"))
        if review is not None and review.approved:
            return "__finalize__"
        if rounds_completed >= max_iterations:
            return "__finalize__"
        return worker_step

    finalize_node = f"__{worker_step}_finalize__"

    # LangGraph's add_node overloads unify a node's parameter type against
    # NodeInputT strictly enough that a callable returning a *partial*
    # state update (dict[str, Any], the standard LangGraph node shape used
    # throughout this module) rather than the full WorkflowState doesn't
    # resolve to any overload -- a known friction point in langgraph's
    # stubs for this common pattern, not a real type error: every node
    # here is exercised end-to-end by tests/unit/test_workflow_primitives.py
    # and tests/unit/test_workflow_compiler.py.
    graph.add_node(worker_step, worker_node)  # type: ignore[call-overload]
    graph.add_node(reviewer_step, reviewer_node)  # type: ignore[call-overload]
    graph.add_node(finalize_node, finalize_draft)  # type: ignore[call-overload]
    graph.add_edge(worker_step, reviewer_step)
    graph.add_conditional_edges(
        reviewer_step,
        route_after_review,
        {worker_step: worker_step, "__finalize__": finalize_node},
    )
    graph.add_edge(finalize_node, END)


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
