"""The built-in workflows' own test suites, run in CI (issue #84 slice B).

Every built-in workflow's `tests:` run here through the real eval-run path
(start, then advance until done) against a scripted fake model. Only
structural checks are asserted - route taken, review rounds, tool called -
since those depend on how the workflow is wired, which a script can
exercise; content checks need a real model and run from the Workflows
screen instead.

A built-in test case added without a script here fails
test_every_built_in_suite_has_a_script, rather than silently going untested.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.tools import StructuredTool

from app.core.auth import get_current_user
from app.core.llm_client import FakeChatModel
from app.main import app
from app.services import workflow_service
from app.workflows import tool_registry
from app.workflows.loader import load_workflow_definitions
from app.workflows.primitives import ReviewResult

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
_WORKFLOWS_DIR = str(Path(__file__).resolve().parents[2] / "workflows")

ADMIN = {
    "user_id": "admin-user-1",
    "username": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "token": {"realm_access": {"roles": ["admin"]}},
    "access_token": "fake-access-token",
}


def _search_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[ToolCall(name="search_knowledge_base", args={"query": "q"}, id="call-1")],
    )


# The model's replies across each built-in suite, in suite order.
SCRIPTS: dict[str, FakeChatModel] = {
    "chat": FakeChatModel(responses=[_search_call(), AIMessage(content="25 days.")]),
    "triage": FakeChatModel(
        responses=[
            AIMessage(content="technical"),
            AIMessage(content="Install the client, then import the profile."),
            AIMessage(content="general"),
            AIMessage(content="How about 'Summit Days'?"),
        ]
    ),
    # Three runs of interpret -> worker -> reviewer, approved first round.
    "reviewed_answer": FakeChatModel(
        responses=[AIMessage(content="Summarize the policy."), AIMessage(content="A draft.")] * 3,
        structured_responses=[ReviewResult(approved=True)] * 3,
    ),
}


async def _no_results(query: str) -> tuple[str, list]:
    return "No matching documents.", []


_NO_RESULTS_TOOL = StructuredTool.from_function(
    coroutine=_no_results,
    name="search_knowledge_base",
    description="Search the knowledge base.",
    response_format="content_and_artifact",
)


def _built_in_suites() -> dict[str, int]:
    return {
        name: len(definition.tests)
        for name, definition in load_workflow_definitions(_WORKFLOWS_DIR).items()
        if definition.tests
    }


@pytest.mark.unit
def test_every_built_in_suite_has_a_script():
    assert set(SCRIPTS) == set(_built_in_suites())


@pytest.mark.unit
@pytest.mark.parametrize("workflow_name", sorted(SCRIPTS))
def test_built_in_suite_passes_its_structural_checks(
    client, db_session, monkeypatch, workflow_name
):
    model = SCRIPTS[workflow_name].model_copy(deep=True)
    monkeypatch.setattr("app.workflows.compiler.get_llm_client", lambda db: model)
    monkeypatch.setitem(
        tool_registry._TOOL_REGISTRY, "search_knowledge_base", lambda token, url: _NO_RESULTS_TOOL
    )
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    try:
        version_id = workflow_service.resolve_active_workflow(
            db_session, workflow_name, now=NOW
        ).version_id
        run = client.post(f"/api/workflows/{workflow_name}/versions/{version_id}/eval-runs").json()
        while run["status"] == "running":
            run = client.post(
                f"/api/workflows/{workflow_name}/eval-runs/{run['id']}/advance"
            ).json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    failed_structural_checks = [
        (case["name"], result["run_index"], check["detail"])
        for case in run["cases"]
        for result in case["results"]
        for check in result["checks"]
        if check["kind"] == "structural" and not check["passed"]
    ]
    assert run["status"] == "completed"
    assert failed_structural_checks == []
    assert len(run["cases"]) == _built_in_suites()[workflow_name]
