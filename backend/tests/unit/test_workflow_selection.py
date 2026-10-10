"""Choosing a workflow in chat (issue #85, epic #80 slice 5/5) - TDD.

User feature: any authenticated user can list the *published* workflows
and start a conversation with one. The conversation is bound to that
workflow on the server; drafts and unpublished workflows can never run.
"""

from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage

from app.core.auth import get_current_user
from app.core.llm_client import FakeChatModel
from app.db.models import ChatTurnVersion, ConversationThread
from app.main import app
from app.services import workflow_service
from app.workflows.schema import parse_workflow_definition

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

USER = {
    "user_id": "chat-user-1",
    "username": "chatter",
    "email": "chatter@example.com",
    "name": "Chat User",
    "token": {"realm_access": {"roles": []}},
    "access_token": "fake-access-token",
}

GENERAL_SPECIALIST_PROMPT = (
    "You are a general-purpose assistant for non-technical questions. Be brief, direct, "
    "and helpful."
)


@pytest.fixture
def as_user():
    app.dependency_overrides[get_current_user] = lambda: USER
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def scripted_llm(monkeypatch):
    """Route `triage` to its general specialist, then answer."""
    fake = FakeChatModel(
        responses=[AIMessage(content="general"), AIMessage(content="A general answer.")]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake)
    return fake


def _create_unpublished(db, name="summarizer"):
    workflow_service.resolve_active_workflow(db, "chat", now=NOW)  # seed built-ins
    workflow_service.create_workflow(
        db,
        yaml_text=(
            f"name: {name}\nversion: 1\nentry: s\nsteps:\n"
            "  s:\n    type: agent\n    prompt: Summarize.\n"
        ),
        change_note="new",
        actor_user_id="admin-1",
        now=NOW,
    )
    db.commit()


# --- schema -------------------------------------------------------------


@pytest.mark.unit
def test_a_workflow_can_carry_a_description_shown_to_users():
    definition = parse_workflow_definition(
        {
            "name": "x",
            "version": 1,
            "description": "Routes your question to a specialist.",
            "entry": "s",
            "steps": {"s": {"type": "agent", "prompt": "p"}},
        },
        source_file="x.yaml",
    )

    assert definition.description == "Routes your question to a specialist."


@pytest.mark.unit
def test_guarded_prompt_text_covers_every_step_prompt():
    """The output guardrail must protect every prompt a workflow sends to the
    model, not just an `agent` entry step's - a route-first workflow has no
    single "system prompt"."""
    definition = parse_workflow_definition(
        {
            "name": "x",
            "version": 1,
            "entry": "pick",
            "steps": {
                "pick": {"type": "route", "prompt": "ROUTE-PROMPT", "branches": {"a": "answer"}},
                "answer": {"type": "agent", "prompt": "AGENT-PROMPT", "next": "check"},
                "check": {
                    "type": "review_loop",
                    "worker_step": "w",
                    "reviewer_step": "r",
                    "worker_prompt": "WORKER-PROMPT",
                    "reviewer_prompt": "REVIEWER-PROMPT",
                    "max_iterations": 2,
                },
            },
        },
        source_file="x.yaml",
    )

    text = definition.guarded_prompt_text()

    for prompt in ("ROUTE-PROMPT", "AGENT-PROMPT", "WORKER-PROMPT", "REVIEWER-PROMPT"):
        assert prompt in text


# --- listing ------------------------------------------------------------


@pytest.mark.unit
def test_any_signed_in_user_can_list_published_workflows(client, db_session, as_user):
    response = client.get("/api/agents/workflows")

    assert response.status_code == 200
    workflows = response.json()["workflows"]
    names = [w["name"] for w in workflows]
    assert names[0] == "chat", "the default comes first"
    assert {"chat", "triage", "reviewed_answer"} <= set(names)
    assert all(w["description"] for w in workflows), "every built-in describes itself"
    assert [w["is_default"] for w in workflows].count(True) == 1


@pytest.mark.unit
def test_unpublished_workflows_are_not_listed(client, db_session, as_user):
    _create_unpublished(db_session)

    names = [w["name"] for w in client.get("/api/agents/workflows").json()["workflows"]]

    assert "summarizer" not in names


@pytest.mark.unit
def test_listing_workflows_requires_sign_in(client):
    assert client.get("/api/agents/workflows").status_code == 403


# --- binding ------------------------------------------------------------


@pytest.mark.unit
def test_a_new_conversation_without_a_choice_uses_the_default_chat_workflow(
    client, db_session, as_user
):
    response = client.post("/api/agents/chat", json={"message": "hi"})

    thread = db_session.get(ConversationThread, response.json()["thread_id"])
    assert thread.workflow_name == "chat"


@pytest.mark.unit
def test_a_conversation_started_with_a_workflow_is_answered_by_it(
    client, db_session, as_user, scripted_llm
):
    response = client.post("/api/agents/chat", json={"message": "hi", "workflow": "triage"})

    assert response.status_code == 200
    assert response.json()["response"] == "A general answer."
    assert response.json()["workflow"] == "triage"
    turn = db_session.query(ChatTurnVersion).one()
    assert turn.workflow_name == "triage"


@pytest.mark.unit
def test_a_follow_up_keeps_the_conversations_workflow_whatever_the_client_asks(
    client, db_session, as_user, scripted_llm
):
    """The binding is enforced on the server: a client cannot switch an
    existing conversation to another workflow mid-thread."""
    first = client.post("/api/agents/chat", json={"message": "hi", "workflow": "triage"})
    scripted_llm.responses = [AIMessage(content="general"), AIMessage(content="Still triage.")]

    follow_up = client.post(
        "/api/agents/chat",
        json={"message": "again", "thread_id": first.json()["thread_id"], "workflow": "chat"},
    )

    assert follow_up.json()["thread_id"] == first.json()["thread_id"]
    assert follow_up.json()["workflow"] == "triage"
    assert follow_up.json()["response"] == "Still triage."


@pytest.mark.unit
@pytest.mark.parametrize("workflow", ["summarizer", "does_not_exist"])
def test_an_unpublished_or_unknown_workflow_cannot_be_started(
    client, db_session, as_user, workflow
):
    _create_unpublished(db_session)

    response = client.post("/api/agents/chat", json={"message": "hi", "workflow": workflow})

    assert response.status_code == 400
    assert response.json()["detail"] == "workflow_not_available"
    assert response.json()["message"]
    assert db_session.query(ConversationThread).count() == 0


@pytest.mark.unit
def test_threads_report_their_workflow(client, db_session, as_user, scripted_llm):
    thread_id = client.post(
        "/api/agents/chat", json={"message": "hi", "workflow": "triage"}
    ).json()["thread_id"]

    listed = client.get("/api/agents/threads").json()["threads"]
    history = client.get(f"/api/agents/threads/{thread_id}").json()

    assert listed[0]["workflow"] == "triage"
    assert history["workflow"] == "triage"


# --- guardrail ----------------------------------------------------------


@pytest.mark.unit
def test_output_guardrail_protects_a_route_first_workflows_prompts(
    client, db_session, as_user, monkeypatch
):
    """triage starts with a route step, which has no single system prompt.
    A reply that echoes one of its specialist prompts must still be redacted."""
    fake = FakeChatModel(
        responses=[
            AIMessage(content="general"),
            AIMessage(content=f"My instructions: {GENERAL_SPECIALIST_PROMPT}"),
        ]
    )
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: fake)

    response = client.post("/api/agents/chat", json={"message": "hi", "workflow": "triage"})

    assert response.json()["was_modified"] is True
    assert "non-technical questions" not in response.json()["response"]
