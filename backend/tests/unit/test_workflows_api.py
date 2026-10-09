"""Unit tests for the admin-only /api/workflows endpoints (issue #83) - TDD.

Admin feature: every route is gated by require_admin. These endpoints back
the Workflows screen: list, history, version detail, diff, diagram, save
draft, publish, rollback.
"""

from datetime import datetime, timezone

import pytest

from app.core.auth import get_current_user
from app.db.models import AuditLog
from app.main import app
from app.services.workflow_service import sync_builtin_versions

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

ADMIN_USER = {
    "user_id": "admin-user-1",
    "username": "admin",
    "email": "admin@example.com",
    "name": "Admin User",
    "token": {"realm_access": {"roles": ["admin"]}},
}
NON_ADMIN_USER = {
    "user_id": "regular-user-1",
    "username": "regular",
    "email": "regular@example.com",
    "name": "Regular User",
    "token": {"realm_access": {"roles": ["offline_access"]}},
}

CHAT_BUILTIN = (
    "name: chat\nversion: 1\nentry: respond\nsteps:\n"
    "  respond:\n    type: agent\n    prompt: You are helpful.\n"
)
CHAT_EDITED = CHAT_BUILTIN.replace("You are helpful.", "You are helpful and terse.")


@pytest.fixture
def seeded(db_session):
    sync_builtin_versions(db_session, {"chat": CHAT_BUILTIN}, now=NOW)
    db_session.commit()
    return db_session


@pytest.fixture
def as_admin():
    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _versions(client):
    return client.get("/api/workflows/chat/versions").json()["versions"]


def _save(client, yaml_text=CHAT_EDITED, note="terser"):
    return client.post(
        "/api/workflows/chat/versions", json={"yaml_text": yaml_text, "change_note": note}
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/workflows", None),
        ("post", "/api/workflows", {"yaml_text": "x", "change_note": "y"}),
        ("get", "/api/workflows/chat/versions", None),
        ("get", "/api/workflows/chat/versions/some-id", None),
        ("get", "/api/workflows/chat/versions/some-id/graph", None),
        ("get", "/api/workflows/chat/diff?from_version=a&to_version=b", None),
        ("post", "/api/workflows/chat/versions", {"yaml_text": "x", "change_note": "y"}),
        ("post", "/api/workflows/chat/publish", {"version_id": "x"}),
        ("post", "/api/workflows/chat/rollback", {"version_id": "x"}),
    ],
)
def test_every_workflow_route_is_admin_only(client, seeded, method, path, body):
    app.dependency_overrides[get_current_user] = lambda: NON_ADMIN_USER

    response = getattr(client, method)(path, **({"json": body} if body else {}))

    app.dependency_overrides.clear()
    assert response.status_code == 403


@pytest.mark.unit
def test_list_shows_each_workflow_and_the_change_management_mode(client, seeded, as_admin):
    response = client.get("/api/workflows")

    assert response.status_code == 200
    body = response.json()
    assert body["change_management_mode"] == "direct"
    [chat] = body["workflows"]
    assert chat["name"] == "chat"
    assert chat["active_version_sequence"] == 1
    assert chat["active_version_source"] == "builtin"
    assert chat["builtin_update_available"] is False


@pytest.mark.unit
def test_save_draft_returns_the_new_unpublished_version(client, seeded, as_admin):
    response = _save(client)

    assert response.status_code == 201
    body = response.json()
    assert body["sequence"] == 2
    assert body["source"] == "admin"
    assert body["is_active"] is False
    assert body["yaml_text"] == CHAT_EDITED
    assert body["change_note"] == "terser"
    assert body["author_user_id"] == "admin-user-1"


@pytest.mark.unit
def test_invalid_draft_is_a_422_naming_the_field(client, seeded, as_admin):
    response = _save(client, CHAT_BUILTIN.replace("entry: respond", "entry: nowhere"))

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "workflow_draft_rejected"
    assert body["field"] == "entry"
    assert "nowhere" in body["message"]


@pytest.mark.unit
def test_change_note_is_required(client, seeded, as_admin):
    response = _save(client, note="  ")

    assert response.status_code == 422
    assert response.json()["field"] == "change_note"


@pytest.mark.unit
def test_unknown_workflow_is_404(client, seeded, as_admin):
    response = client.post(
        "/api/workflows/brand_new/versions", json={"yaml_text": CHAT_EDITED, "change_note": "x"}
    )

    assert response.status_code == 404


@pytest.mark.unit
def test_history_is_newest_first_and_marks_the_active_version(client, seeded, as_admin):
    _save(client)

    versions = _versions(client)

    assert [v["sequence"] for v in versions] == [2, 1]
    assert [v["is_active"] for v in versions] == [False, True]
    assert "yaml_text" not in versions[0], "the history list should stay light; detail has the YAML"


@pytest.mark.unit
def test_publish_then_rollback_moves_the_active_version_and_is_audited(
    client, seeded, as_admin, db_session
):
    draft_id = _save(client).json()["id"]
    builtin_id = _versions(client)[1]["id"]

    publish = client.post("/api/workflows/chat/publish", json={"version_id": draft_id})
    after_publish = _versions(client)
    rollback = client.post("/api/workflows/chat/rollback", json={"version_id": builtin_id})
    after_rollback = _versions(client)

    assert publish.status_code == 200
    assert after_publish[0]["is_active"] is True
    assert rollback.status_code == 200
    assert after_rollback[1]["is_active"] is True
    actions = [
        e.action for e in db_session.query(AuditLog).filter(AuditLog.field_name == "chat").all()
    ]
    assert actions.count("workflow.published") == 1
    assert actions.count("workflow.rolled_back") == 1


@pytest.mark.unit
def test_publish_unknown_version_is_404(client, seeded, as_admin):
    response = client.post("/api/workflows/chat/publish", json={"version_id": "does-not-exist"})

    assert response.status_code == 404


@pytest.mark.unit
def test_version_detail_includes_yaml(client, seeded, as_admin):
    builtin_id = _versions(client)[0]["id"]

    response = client.get(f"/api/workflows/chat/versions/{builtin_id}")

    assert response.status_code == 200
    assert response.json()["yaml_text"] == CHAT_BUILTIN


@pytest.mark.unit
def test_diff_between_two_versions(client, seeded, as_admin):
    draft_id = _save(client).json()["id"]
    builtin_id = _versions(client)[1]["id"]

    response = client.get(
        f"/api/workflows/chat/diff?from_version={builtin_id}&to_version={draft_id}"
    )

    assert response.status_code == 200
    assert "+    prompt: You are helpful and terse." in response.json()["diff"]


@pytest.mark.unit
def test_graph_describes_the_version_steps(client, seeded, as_admin):
    builtin_id = _versions(client)[0]["id"]

    response = client.get(f"/api/workflows/chat/versions/{builtin_id}/graph")

    assert response.status_code == 200
    assert response.json() == {
        "entry": "respond",
        "nodes": [{"id": "respond", "type": "agent"}],
        "edges": [],
    }


@pytest.mark.unit
def test_oversized_yaml_is_rejected_at_the_request_boundary(client, seeded, as_admin):
    from app.services.workflow_service import MAX_WORKFLOW_YAML_BYTES

    response = _save(client, CHAT_BUILTIN + "#" * (MAX_WORKFLOW_YAML_BYTES + 1))

    assert response.status_code == 422


@pytest.mark.unit
def test_create_workflow_then_it_appears_unpublished(client, seeded, as_admin):
    yaml_text = (
        "name: summarizer\nversion: 1\nentry: summarize\nsteps:\n"
        "  summarize:\n    type: agent\n    prompt: Summarize in one line.\n"
    )

    created = client.post("/api/workflows", json={"yaml_text": yaml_text, "change_note": "new"})
    duplicate = client.post("/api/workflows", json={"yaml_text": yaml_text, "change_note": "again"})
    listed = {w["name"]: w for w in client.get("/api/workflows").json()["workflows"]}

    assert created.status_code == 201
    assert created.json()["workflow_name"] == "summarizer"
    assert duplicate.status_code == 409
    assert listed["summarizer"]["active_version_id"] is None
