"""Tests for the workflow engine's graph-building primitives.

Each primitive is exercised in isolation, directly building a small
StateGraph by hand (not through YAML/the compiler — that's
test_workflow_compiler.py's job) so a primitive's own behavior is pinned
independently of how a definition gets parsed.
"""

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

from app.agents.checkpointer import SqlAlchemyCheckpointSaver
from app.core.llm_client import FakeChatModel
from app.repositories import ThreadRepository
from app.workflows.primitives import (
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


def test_review_loop_worker_then_approving_reviewer_ends_immediately(db_session):
    """A reviewer that approves on the first pass exits the loop after one
    worker/reviewer round.
    """
    worker_llm = FakeChatModel(response="draft answer")
    reviewer_llm = FakeChatModel(response="approve")

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_node=build_agent_node(
            llm=worker_llm, system_prompt="Do the work.", step_name="worker"
        ),
        reviewer_node=build_agent_node(
            llm=reviewer_llm, system_prompt="Review it.", step_name="reviewer"
        ),
        approve_keyword="approve",
        max_iterations=3,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert worker_llm.call_count == 1
    assert reviewer_llm.call_count == 1
    assert result["step_outputs"]["reviewer"] == "approve"


def test_review_loop_rejects_once_then_approves(db_session):
    """The evaluator-optimizer pattern: a reviewer that rejects once sends
    the worker back for a second pass, then approves.
    """
    worker_llm = FakeChatModel(
        responses=[AIMessage(content="draft v1"), AIMessage(content="draft v2")]
    )
    reviewer_llm = FakeChatModel(
        responses=[AIMessage(content="reject: needs more detail"), AIMessage(content="approve")]
    )

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_node=build_agent_node(
            llm=worker_llm, system_prompt="Do the work.", step_name="worker"
        ),
        reviewer_node=build_agent_node(
            llm=reviewer_llm, system_prompt="Review it.", step_name="reviewer"
        ),
        approve_keyword="approve",
        max_iterations=3,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert worker_llm.call_count == 2
    assert reviewer_llm.call_count == 2
    assert result["step_outputs"]["reviewer"] == "approve"


def test_review_loop_stops_at_max_iterations_even_if_never_approved(db_session):
    """A reviewer that never approves must not loop forever — the loop ends
    once max_iterations worker/reviewer rounds have run, surfacing
    whatever the worker last produced rather than hanging the request.
    """
    reviewer_llm = FakeChatModel(response="reject: still not good enough")

    graph = StateGraph(WorkflowState)
    build_review_loop(
        graph,
        worker_step="worker",
        reviewer_step="reviewer",
        worker_node=build_agent_node(
            llm=FakeChatModel(response="draft"), system_prompt="Do the work.", step_name="worker"
        ),
        reviewer_node=build_agent_node(
            llm=reviewer_llm, system_prompt="Review it.", step_name="reviewer"
        ),
        approve_keyword="approve",
        max_iterations=2,
    )
    graph.set_entry_point("worker")
    compiled = graph.compile(checkpointer=SqlAlchemyCheckpointSaver(db_session))

    thread_id = _new_thread(db_session)
    result = compiled.invoke(
        _base_state(thread_id), config={"configurable": {"thread_id": thread_id}}
    )

    assert reviewer_llm.call_count == 2
    assert result["step_outputs"]["reviewer"] == "reject: still not good enough"
