"""Tests for compiling a validated WorkflowDef into a runnable LangGraph
StateGraph (app.workflows.compiler.compile_workflow).

Uses app.workflows.schema.parse_workflow_definition to build the
WorkflowDef under test (the same path the loader uses), so these tests
exercise the schema -> compiler boundary the way it's actually used, not
a hand-built WorkflowDef the schema would never produce.
"""

from langchain_core.messages import AIMessage, HumanMessage

from app.core.llm_client import FakeChatModel
from app.repositories import ThreadRepository
from app.workflows.compiler import compile_workflow
from app.workflows.primitives import ReviewResult
from app.workflows.schema import parse_workflow_definition

_UNUSED_TOKEN = "unused-token"
_UNREACHABLE_MCP_URL = "http://localhost:1/mcp"


def _new_thread(db_session, user_id: str = "test-user") -> str:
    thread = ThreadRepository(db_session).get_or_create_owned(None, user_id)
    db_session.commit()
    return thread.id


def test_compile_single_agent_workflow_runs_like_chat_agent(db_session, monkeypatch):
    """A one-step agent workflow (the shape chat.yaml uses) behaves exactly
    like today's hand-coded chat_agent for a message with no tool call.
    """
    monkeypatch.setattr(
        "app.workflows.compiler.get_llm_client", lambda db: FakeChatModel(response="4")
    )
    raw = {
        "name": "chat",
        "version": 1,
        "entry": "respond",
        "steps": {
            "respond": {
                "type": "agent",
                "prompt": "You are a helpful assistant.",
                "tools": ["search_knowledge_base"],
            }
        },
    }
    definition = parse_workflow_definition(raw, source_file="chat.yaml")
    graph = compile_workflow(
        definition, db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )

    thread_id = _new_thread(db_session)
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="What is 2+2?")],
            "thread_id": thread_id,
            "user_id": "test-user",
            "step_outputs": {},
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    final_message = result["messages"][-1]
    assert isinstance(final_message, AIMessage)
    assert final_message.content == "4"


def test_compile_sequence_workflow_chains_two_agent_steps(db_session, monkeypatch):
    """draft -> polish, wired via `next`, runs both steps in order."""
    # One shared FakeChatModel instance across both steps: compile_workflow
    # calls get_llm_client(db) once per agent step, and each step's call
    # must draw from the *same* response queue in invocation order (draft
    # first, then polish) -- a fresh FakeChatModel per step would reset
    # call_count to 0 each time and always return the first scripted
    # response.
    shared_llm = FakeChatModel(
        responses=[AIMessage(content="draft text"), AIMessage(content="polished text")]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: shared_llm)

    raw = {
        "name": "draft_and_polish",
        "version": 1,
        "entry": "draft",
        "steps": {
            "draft": {"type": "agent", "prompt": "Draft a reply.", "next": "polish"},
            "polish": {"type": "agent", "prompt": "Polish the reply."},
        },
    }
    definition = parse_workflow_definition(raw, source_file="draft_and_polish.yaml")
    graph = compile_workflow(
        definition, db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )

    thread_id = _new_thread(db_session)
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="hello")],
            "thread_id": thread_id,
            "user_id": "test-user",
            "step_outputs": {},
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["messages"][-1].content == "polished text"
    assert result["step_outputs"]["draft"] == "draft text"
    assert result["step_outputs"]["polish"] == "polished text"


async def test_compile_review_loop_workflow_reaches_approval(db_session, monkeypatch):
    """A YAML-defined review_loop step compiles and runs the same
    reject-then-approve cycle app.workflows.primitives.build_review_loop
    is unit-tested against directly, with the reviewer's structured
    ReviewResult driving the loop instead of a keyword match.

    ainvoke, not invoke: a review_loop's worker node is async (see
    build_review_loop's docstring).
    """
    # get_llm_client is called once for the worker, once for the reviewer
    # (app.workflows.compiler._attach_review_loop_step); both resolve to
    # this one shared FakeChatModel here, so its prose `responses` queue
    # (worker) and structured_responses queue (reviewer) are consumed
    # independently, each in the order its own primitive invokes it.
    llm = FakeChatModel(
        responses=[AIMessage(content="draft v1"), AIMessage(content="draft v2")],
        structured_responses=[
            ReviewResult(approved=False, issues=["needs more detail"]),
            ReviewResult(approved=True, issues=[]),
        ],
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "worker",
        "steps": {
            "worker": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Draft an answer to: {task}",
                "reviewer_prompt": "Review the draft: {draft}",
                "max_iterations": 3,
            }
        },
    }
    definition = parse_workflow_definition(raw, source_file="reviewed_answer.yaml")
    graph = compile_workflow(
        definition, db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )

    thread_id = _new_thread(db_session)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Explain X.")],
            "thread_id": thread_id,
            "user_id": "test-user",
            "step_outputs": {},
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["review"].approved is True
    assert llm.call_count == 2
    assert llm.structured_call_count == 2
    assert result["messages"][-1].content == "draft v2"


def test_compile_route_workflow_dispatches_to_matching_branch(db_session, monkeypatch):
    """A YAML-defined route step classifies, then dispatches to the
    matching branch's agent step.
    """
    # The classifier's first call must return "billing" so the route
    # primitive dispatches to billing_agent; billing_agent's own call then
    # draws the next scripted response from the same shared instance,
    # since compile_workflow resolves get_llm_client(db) once per step and
    # this test patches it to always return this one shared FakeChatModel.
    shared_llm = FakeChatModel(
        responses=[AIMessage(content="billing"), AIMessage(content="billing reply")]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: shared_llm)

    raw = {
        "name": "triage",
        "version": 1,
        "entry": "classify",
        "steps": {
            "classify": {
                "type": "route",
                "prompt": "Classify the request as billing or support.",
                "branches": {"billing": "billing_agent", "support": "support_agent"},
            },
            "billing_agent": {"type": "agent", "prompt": "Handle billing."},
            "support_agent": {"type": "agent", "prompt": "Handle support."},
        },
    }
    definition = parse_workflow_definition(raw, source_file="triage.yaml")
    graph = compile_workflow(
        definition, db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )

    thread_id = _new_thread(db_session)
    result = graph.invoke(
        {
            "messages": [HumanMessage(content="I have a billing question")],
            "thread_id": thread_id,
            "user_id": "test-user",
            "step_outputs": {},
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["step_outputs"]["classify"] == "billing"
    assert result["messages"][-1].content == "billing reply"


async def test_compile_agent_next_into_review_loop_resolves_to_worker_node(db_session, monkeypatch):
    """An `agent` step's `next` pointing at a review_loop step's top-level
    name (as reviewed_answer.yaml's `interpret` -> `draft_and_review`
    does) must wire the edge to that review_loop's *worker* node, not a
    nonexistent node named after the top-level step -- the compiler's
    entry_nodes resolution must apply to a `next` edge, not just
    set_entry_point. Also exercises output_field="task": the interpreter's
    response lands in state["task"], not `messages`.
    """
    llm = FakeChatModel(
        responses=[AIMessage(content="Restated task."), AIMessage(content="draft answer")],
        structured_responses=[ReviewResult(approved=True, issues=[])],
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "interpret",
        "steps": {
            "interpret": {
                "type": "agent",
                "prompt": "Restate the request as a task.",
                "output_field": "task",
                "next": "draft_and_review",
            },
            "draft_and_review": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Complete: {task}",
                "reviewer_prompt": "Review: {draft}",
                "max_iterations": 3,
            },
        },
    }
    definition = parse_workflow_definition(raw, source_file="reviewed_answer.yaml")
    graph = compile_workflow(
        definition, db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )

    thread_id = _new_thread(db_session)
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Explain X.")],
            "thread_id": thread_id,
            "user_id": "test-user",
            "step_outputs": {},
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["task"] == "Restated task."
    assert result["messages"][-1].content == "draft answer"
    assert all(m.content != "Restated task." for m in result["messages"])
