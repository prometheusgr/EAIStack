"""Tests for the built-in reference workflows shipped by issue #82:
backend/workflows/reviewed_answer.yaml (interpret -> work -> review loop)
and backend/workflows/triage.yaml (route to specialists).

Loaded and compiled the same way app.main's lifespan hook and
app.agents.registry do at process startup (via
app.workflows.loader.load_workflow_definitions against the real, shipped
workflows/ directory), not hand-built WorkflowDefs -- so a regression in
either shipped file fails these tests too, matching
test_chat_workflow.py's own pattern for chat.yaml.

Not wired to any HTTP endpoint yet (workflow selection in chat is issue
#85's scope) -- these tests exercise the compiled graphs directly.
"""

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.llm_client import FakeChatModel
from app.repositories import ThreadRepository
from app.workflows.compiler import compile_workflow
from app.workflows.loader import load_workflow_definitions
from app.workflows.primitives import ReviewResult

_UNUSED_TOKEN = "unused-token"
_UNREACHABLE_MCP_URL = "http://localhost:1/mcp"

_WORKFLOWS_DIR = str(Path(__file__).resolve().parents[2] / "workflows")


def _new_thread(db_session, user_id: str = "test-user") -> str:
    thread = ThreadRepository(db_session).get_or_create_owned(None, user_id)
    db_session.commit()
    return thread.id


def _initial_state(message: str, thread_id: str, user_id: str = "test-user") -> dict:
    return {
        "messages": [HumanMessage(content=message)],
        "thread_id": thread_id,
        "user_id": user_id,
        "step_outputs": {},
    }


@pytest.mark.unit
def test_all_built_in_workflows_load_and_validate():
    """The full built-in set -- chat, reviewed_answer, triage -- parses and
    validates cleanly together, the same load app.main's lifespan hook
    performs at startup. A broken file here would fail the container at
    boot (see test_main_lifespan.py's dedicated failure-path test), so this
    is the "no regression in the shipped set" smoke test.
    """
    definitions = load_workflow_definitions(_WORKFLOWS_DIR)

    assert set(definitions.keys()) >= {"chat", "reviewed_answer", "triage"}


# ---------------------------------------------------------------------------
# reviewed_answer.yaml: interpret -> work -> review loop
# ---------------------------------------------------------------------------


def _compile_reviewed_answer(db_session):
    definitions = load_workflow_definitions(_WORKFLOWS_DIR)
    return compile_workflow(
        definitions["reviewed_answer"],
        db=db_session,
        token=_UNUSED_TOKEN,
        mcp_url=_UNREACHABLE_MCP_URL,
    )


@pytest.mark.unit
async def test_reviewed_answer_interpret_then_worker_approved_on_first_pass(
    db_session, monkeypatch
):
    """interpret restates the task (state["task"]), then the worker drafts
    and the reviewer approves immediately -- one round, one visible
    message.

    ainvoke, not invoke: reviewed_answer.yaml's worker step is async (see
    build_review_loop's docstring).
    """
    llm = FakeChatModel(
        responses=[
            AIMessage(content="Explain what mitochondria do."),  # interpret
            AIMessage(content="Mitochondria produce ATP via cellular respiration."),  # worker
        ],
        structured_responses=[ReviewResult(approved=True, issues=[])],
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    graph = _compile_reviewed_answer(db_session)
    thread_id = _new_thread(db_session)

    result = await graph.ainvoke(
        _initial_state("what do mitochondria do?", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["task"] == "Explain what mitochondria do."
    assert result["review"].approved is True
    assert result["messages"][-1].content == "Mitochondria produce ATP via cellular respiration."


@pytest.mark.unit
async def test_reviewed_answer_worker_revises_after_rejection(db_session, monkeypatch):
    """A reviewer that rejects once sends the worker back for a revision;
    only the second (approved) draft reaches the visible transcript -- the
    first draft and both reviewer verdicts never do.
    """
    llm = FakeChatModel(
        responses=[
            AIMessage(content="Explain photosynthesis."),  # interpret
            AIMessage(content="Plants make food from sunlight."),  # worker round 1
            AIMessage(
                content=(
                    "Photosynthesis converts light energy into chemical energy stored as "
                    "glucose, using carbon dioxide and water, and releases oxygen."
                )
            ),  # worker round 2
        ],
        structured_responses=[
            ReviewResult(approved=False, issues=["too vague, missing the chemical process"]),
            ReviewResult(approved=True, issues=[]),
        ],
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    graph = _compile_reviewed_answer(db_session)
    thread_id = _new_thread(db_session)

    result = await graph.ainvoke(
        _initial_state("what is photosynthesis?", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["review"].approved is True
    assert result["messages"][-1].content.startswith("Photosynthesis converts light energy")
    assert all("make food from sunlight" not in m.content for m in result["messages"])


@pytest.mark.unit
async def test_reviewed_answer_stops_at_max_iterations(db_session, monkeypatch):
    """A reviewer that never approves doesn't hang the request -- the loop
    ends at the YAML's declared max_iterations (3), surfacing the worker's
    last draft.
    """
    llm = FakeChatModel(
        responses=[AIMessage(content="Task restated.")],
        structured_responses=[ReviewResult(approved=False, issues=["never good enough"])],
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    graph = _compile_reviewed_answer(db_session)
    thread_id = _new_thread(db_session)

    result = await graph.ainvoke(
        _initial_state("anything", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["review"].approved is False
    # interpret (1) + worker rounds (3, the YAML's max_iterations) = 4 prose calls.
    assert llm.call_count == 4
    assert llm.structured_call_count == 3


# ---------------------------------------------------------------------------
# triage.yaml: route to specialists
# ---------------------------------------------------------------------------


def _compile_triage(db_session):
    definitions = load_workflow_definitions(_WORKFLOWS_DIR)
    return compile_workflow(
        definitions["triage"], db=db_session, token=_UNUSED_TOKEN, mcp_url=_UNREACHABLE_MCP_URL
    )


@pytest.mark.unit
def test_triage_routes_to_technical_specialist(db_session, monkeypatch):
    llm = FakeChatModel(
        responses=[AIMessage(content="technical"), AIMessage(content="Try restarting the service.")]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    graph = _compile_triage(db_session)
    thread_id = _new_thread(db_session)

    result = graph.invoke(
        _initial_state("my server keeps crashing", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["step_outputs"]["classify"] == "technical"
    assert result["messages"][-1].content == "Try restarting the service."


@pytest.mark.unit
def test_triage_routes_to_general_specialist(db_session, monkeypatch):
    llm = FakeChatModel(
        responses=[AIMessage(content="general"), AIMessage(content="Our office hours are 9-5.")]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: llm)

    graph = _compile_triage(db_session)
    thread_id = _new_thread(db_session)

    result = graph.invoke(
        _initial_state("what are your office hours?", thread_id),
        config={"configurable": {"thread_id": thread_id}},
    )

    assert result["step_outputs"]["classify"] == "general"
    assert result["messages"][-1].content == "Our office hours are 9-5."
