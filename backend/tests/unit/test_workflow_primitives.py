"""Tests for the workflow engine's graph-building primitives.

Each primitive is exercised in isolation, directly building a small
StateGraph by hand (not through YAML/the compiler — that's
test_workflow_compiler.py's job) so a primitive's own behavior is pinned
independently of how a definition gets parsed.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.core.llm_client import FakeChatModel
from app.repositories import ThreadRepository
from app.workflows.primitives import (
    ReviewResult,
    WorkflowState,
    build_agent_node,
    build_review_loop,
    build_route_node,
)


def _new_thread(db_session, user_id: str = "test-user") -> str:
    thread = ThreadRepository(db_session).get_or_create_owned(None, user_id)
    db_session.commit()
    return thread.id


def _base_state(thread_id: str, user_id: str = "test-user") -> WorkflowState:
    return {
        "messages": [HumanMessage(content="hello")],
        "thread_id": thread_id,
        "user_id": user_id,
        "step_outputs": {},
    }


# ---------------------------------------------------------------------------
# agent primitive
# ---------------------------------------------------------------------------


def test_build_agent_node_invokes_llm_and_appends_message(db_session):
    """A single agent node calls the LLM once and appends its response."""
    fake_llm = FakeChatModel(response="4")
    node = build_agent_node(llm=fake_llm, system_prompt="You answer math questions.")

    thread_id = _new_thread(db_session)
    graph = StateGraph(WorkflowState)
    graph.add_node("solve", node)
    graph.set_entry_point("solve")
    graph.add_edge("solve", END)
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    final_message = result["messages"][-1]
    assert isinstance(final_message, AIMessage)
    assert final_message.content == "4"
    assert fake_llm.call_count == 1


def test_build_agent_node_records_step_output(db_session):
    """An agent node records its raw response under its own step name, so a
    downstream route/review_loop primitive can read it without re-scanning
    the whole message list.
    """
    fake_llm = FakeChatModel(response="approved")
    node = build_agent_node(llm=fake_llm, system_prompt="Review the work.", step_name="reviewer")

    thread_id = _new_thread(db_session)
    graph = StateGraph(WorkflowState)
    graph.add_node("reviewer", node)
    graph.set_entry_point("reviewer")
    graph.add_edge("reviewer", END)
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert result["step_outputs"]["reviewer"] == "approved"


# ---------------------------------------------------------------------------
# route primitive
# ---------------------------------------------------------------------------


def test_build_route_node_selects_branch_by_classifier_output(db_session):
    """route dispatches to the branch whose name matches the classifier
    agent's raw text response, generalizing chat_agent's two-way
    tool-call/no-tool-call conditional edge to N named branches.
    """
    fake_llm = FakeChatModel(response="billing")
    classifier = build_agent_node(
        llm=fake_llm, system_prompt="Classify the request.", step_name="classify"
    )
    router = build_route_node(step_name="classify", branches=["billing", "support"])

    thread_id = _new_thread(db_session)
    graph = StateGraph(WorkflowState)
    graph.add_node("classify", classifier)
    graph.add_node("billing", build_agent_node(llm=FakeChatModel(response="billing reply")))
    graph.add_node("support", build_agent_node(llm=FakeChatModel(response="support reply")))
    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", router, {"billing": "billing", "support": "support"})
    graph.add_edge("billing", END)
    graph.add_edge("support", END)
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert result["messages"][-1].content == "billing reply"


def test_build_route_node_falls_back_to_first_branch_on_unrecognized_output(db_session):
    """A classifier response that doesn't match any declared branch name
    must not crash the graph — routing degrades to the first declared
    branch rather than raising, since the classifier is an LLM call and
    LLM output is never fully trustworthy at a system boundary.
    """
    router = build_route_node(step_name="classify", branches=["billing", "support"])
    thread_id = _new_thread(db_session)
    state = _base_state(thread_id)
    state["step_outputs"]["classify"] = "something unrelated"

    assert router(state) == "billing"


# ---------------------------------------------------------------------------
# review_loop primitive
# ---------------------------------------------------------------------------


async def test_review_loop_worker_then_approving_reviewer_ends_immediately(db_session):
    """A reviewer that approves on the first pass exits the loop after one
    worker/reviewer round, and the final message is the worker's draft
    (not the reviewer's structured verdict).

    ainvoke, not invoke: build_review_loop's worker node is async (it must
    support search_knowledge_base, an async-only tool, via worker_tools) --
    see build_review_loop's docstring.
    """
    worker_llm = FakeChatModel(response="draft answer")
    reviewer_llm = FakeChatModel(structured_responses=[ReviewResult(approved=True, issues=[])])

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=worker_llm,
        worker_prompt="Do the work.",
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review it.",
        max_iterations=3,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = await compiled.ainvoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert worker_llm.call_count == 1
    assert reviewer_llm.structured_call_count == 1
    assert result["review"].approved is True
    assert result["messages"][-1].content == "draft answer"


async def test_review_loop_rejects_once_then_approves(db_session):
    """The evaluator-optimizer pattern: a reviewer that rejects once sends
    the worker back for a second pass, then approves. Only the final
    (second) draft reaches `messages` -- the first, rejected draft and
    the reviewer's verdicts never do.
    """
    worker_llm = FakeChatModel(
        responses=[AIMessage(content="draft v1"), AIMessage(content="draft v2")]
    )
    reviewer_llm = FakeChatModel(
        structured_responses=[
            ReviewResult(approved=False, issues=["needs more detail"]),
            ReviewResult(approved=True, issues=[]),
        ]
    )

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=worker_llm,
        worker_prompt="Do the work.",
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review it.",
        max_iterations=3,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = await compiled.ainvoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert worker_llm.call_count == 2
    assert reviewer_llm.structured_call_count == 2
    assert result["review"].approved is True
    assert result["messages"][-1].content == "draft v2"
    assert all(message.content != "draft v1" for message in result["messages"])


async def test_review_loop_stops_at_max_iterations_even_if_never_approved(db_session):
    """A reviewer that never approves must not loop forever — the loop ends
    once max_iterations worker/reviewer rounds have run, surfacing
    whatever the worker last produced rather than hanging the request.
    """
    reviewer_llm = FakeChatModel(
        structured_responses=[ReviewResult(approved=False, issues=["still not good enough"])]
    )

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=FakeChatModel(response="draft"),
        worker_prompt="Do the work.",
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review it.",
        max_iterations=2,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = await compiled.ainvoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert reviewer_llm.structured_call_count == 2
    assert result["review"].approved is False
    assert result["messages"][-1].content == "draft"


async def test_review_loop_treats_malformed_reviewer_output_as_rejection(db_session):
    """A reviewer whose structured-output call raises (malformed/non-
    conforming model output) is treated as an unapproved review, and that
    round still counts against max_iterations -- the loop must not hang
    just because the reviewer never returned parseable JSON.
    """

    class _BrokenStructuredReviewer(FakeChatModel):
        def with_structured_output(self, schema=None, **kwargs):
            from langchain_core.runnables import RunnableLambda

            def _raise(_input):
                raise ValueError("simulated malformed structured output")

            return RunnableLambda(_raise)

    reviewer_llm = _BrokenStructuredReviewer()

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=FakeChatModel(response="draft"),
        worker_prompt="Do the work.",
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review it.",
        max_iterations=2,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = await compiled.ainvoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert result["review"].approved is False
    assert result["review"].issues == ["reviewer output could not be parsed"]
    # Bounded by max_iterations=2 even though every round fails to parse.
    assert result["messages"][-1].content == "draft"


async def test_review_loop_formats_task_and_draft_into_prompts(db_session):
    """worker_prompt/reviewer_prompt may reference {task}/{draft}/
    {review_issues}, substituted from workflow state -- the mechanism a
    review_loop's interpreter-fed task and revision feedback rely on.
    """

    class _RecordingChatModel(FakeChatModel):
        seen_system_prompts: list = []

        async def ainvoke(self, messages, *args, **kwargs):
            system_messages = [m for m in messages if isinstance(m, SystemMessage)]
            if system_messages:
                self.seen_system_prompts.append(system_messages[0].content)
            return await super().ainvoke(messages, *args, **kwargs)

    worker_llm = _RecordingChatModel(response="draft answer")
    worker_llm.seen_system_prompts = []
    reviewer_llm = FakeChatModel(structured_responses=[ReviewResult(approved=True, issues=[])])

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=worker_llm,
        worker_prompt="Complete this task: {task}",
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review against: {task}",
        max_iterations=1,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    state = _base_state(thread_id)
    state["task"] = "Explain photosynthesis"
    await compiled.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    assert worker_llm.seen_system_prompts == ["Complete this task: Explain photosynthesis"]


async def test_review_loop_worker_resolves_tool_calls_and_grounds_final_answer(db_session):
    """A worker bound to worker_tools resolves its own tool calls
    internally, and the tool exchange that grounded the *final* approved
    draft is re-attached to `messages` (not the loop's intermediate
    rounds), so extract_sources_from_messages can find it -- exactly as it
    already does for a plain tool-bound `agent` step.
    """
    from langchain_core.tools import StructuredTool

    calls: list[str] = []

    async def _fake_search(query: str) -> str:
        calls.append(query)
        return f"result for {query}"

    fake_tool = StructuredTool.from_function(
        coroutine=_fake_search, name="search_knowledge_base", description="test tool"
    )

    tool_call_message = AIMessage(
        content="",
        tool_calls=[
            {"name": "search_knowledge_base", "args": {"query": "vacation"}, "id": "call-1"}
        ],
    )
    worker_llm = FakeChatModel(
        responses=[tool_call_message, AIMessage(content="You get 25 days of vacation.")]
    )
    reviewer_llm = FakeChatModel(structured_responses=[ReviewResult(approved=True, issues=[])])

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_llm=worker_llm,
        worker_prompt="Answer using the tool if useful.",
        worker_tools=[fake_tool],
        reviewer_llm=reviewer_llm,
        reviewer_prompt="Review it.",
        max_iterations=1,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = await compiled.ainvoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert calls == ["vacation"]
    assert result["messages"][-1].content == "You get 25 days of vacation."
    tool_messages = [m for m in result["messages"] if type(m).__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    assert "result for vacation" in tool_messages[0].content
