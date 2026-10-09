"""Unit tests for the workflow change-management service (issue #83) - TDD.

Covers the draft -> validate -> publish -> rollback lifecycle, the
audit entry that must accompany every pointer move, and how the built-in
(git-reviewed) workflow files are reconciled with the database store
without ever silently overwriting an admin's published change.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import AuditLog, WorkflowActiveVersion, WorkflowVersion
from app.repositories import AuditLogRepository, WorkflowVersionRepository
from app.services import workflow_service
from app.services.workflow_service import (
    MAX_WORKFLOW_YAML_BYTES,
    WorkflowDraftRejected,
    WorkflowNotFound,
    WorkflowVersionNotFound,
    diff_versions,
    list_workflows,
    publish,
    resolve_active_workflow,
    rollback,
    save_draft,
    sync_builtin_versions,
    workflow_graph,
)

NOW = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)

CHAT_BUILTIN = (
    "name: chat\nversion: 1\nentry: respond\nsteps:\n"
    "  respond:\n    type: agent\n    prompt: You are helpful.\n"
)
CHAT_EDITED = CHAT_BUILTIN.replace("You are helpful.", "You are helpful and terse.")
TRIAGE_BUILTIN = (
    "name: triage\nversion: 1\nentry: classify\nsteps:\n"
    "  classify:\n    type: route\n    prompt: Pick one.\n"
    "    branches:\n      general: answer\n"
    "  answer:\n    type: agent\n    prompt: Answer it.\n"
)


@pytest.fixture
def seeded(db_session):
    """The state app.main's startup leaves behind: every built-in recorded
    as a version and made active."""
    sync_builtin_versions(db_session, {"chat": CHAT_BUILTIN, "triage": TRIAGE_BUILTIN}, now=NOW)
    db_session.commit()
    return db_session


def _active_version_id(db, name="chat"):
    return db.query(WorkflowActiveVersion).filter_by(workflow_name=name).one().version_id


def _actions(db):
    return [entry.action for entry in db.query(AuditLog).order_by(AuditLog.id).all()]


# --- built-in sync -------------------------------------------------------


@pytest.mark.unit
def test_sync_records_each_builtin_as_an_active_builtin_version(seeded):
    version = WorkflowVersionRepository(seeded).latest_for_workflow("chat")

    assert version.source == "builtin"
    assert version.yaml_text == CHAT_BUILTIN
    assert version.author_user_id == "system"
    assert _active_version_id(seeded) == version.id


@pytest.mark.unit
def test_sync_is_idempotent_for_an_unchanged_builtin(seeded):
    sync_builtin_versions(seeded, {"chat": CHAT_BUILTIN, "triage": TRIAGE_BUILTIN}, now=NOW)

    assert seeded.query(WorkflowVersion).filter_by(workflow_name="chat").count() == 1


@pytest.mark.unit
def test_a_changed_builtin_becomes_active_when_no_admin_change_was_published(seeded):
    """A new image shipping a new chat.yaml behaves exactly like it did
    before the store existed - the new file takes effect."""
    newer = CHAT_BUILTIN.replace("You are helpful.", "You are helpful (v2).")

    sync_builtin_versions(seeded, {"chat": newer}, now=NOW + timedelta(days=1))

    active = seeded.get(WorkflowVersion, _active_version_id(seeded))
    assert active.yaml_text == newer
    assert active.source == "builtin"
    assert "workflow.builtin_synced" in _actions(seeded)


@pytest.mark.unit
def test_a_changed_builtin_never_replaces_a_published_admin_version(seeded):
    """Epic #80 invariant 4: a newer built-in never silently overwrites a
    published admin change. It is recorded, and reported as available."""
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )
    publish(seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW)
    newer = CHAT_BUILTIN.replace("You are helpful.", "You are helpful (v2).")

    sync_builtin_versions(seeded, {"chat": newer}, now=NOW + timedelta(days=1))

    assert _active_version_id(seeded) == draft.id
    chat_summary = next(s for s in list_workflows(seeded) if s.name == "chat")
    assert chat_summary.builtin_update_available is True


# --- drafts --------------------------------------------------------------


@pytest.mark.unit
def test_save_draft_stores_an_admin_version_parented_on_the_active_one(seeded):
    builtin_id = _active_version_id(seeded)

    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )

    assert draft.source == "admin"
    assert draft.parent_version_id == builtin_id
    assert draft.author_user_id == "admin-1"
    assert _active_version_id(seeded) == builtin_id, "saving a draft must not publish it"


@pytest.mark.unit
def test_save_draft_is_audit_logged(seeded):
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )

    entry = AuditLogRepository(seeded).list_recent()[0]
    assert (entry.action, entry.field_name, entry.new_value) == (
        "workflow.draft_saved",
        "chat",
        draft.id,
    )
    assert entry.actor_user_id == "admin-1"


@pytest.mark.unit
@pytest.mark.parametrize(
    "yaml_text,expected_field",
    [
        ("name: chat\nversion: 1\nentry: respond\nsteps: [unclosed", "yaml"),
        ("- just\n- a list\n", "<root>"),
        (CHAT_BUILTIN.replace("entry: respond", "entry: nowhere"), "entry"),
        (CHAT_BUILTIN + "    tools: [delete_everything]\n", "steps.respond.tools"),
        (CHAT_BUILTIN.replace("name: chat", "name: impostor"), "name"),
    ],
)
def test_save_draft_rejects_an_invalid_definition_naming_the_field(
    seeded, yaml_text, expected_field
):
    with pytest.raises(WorkflowDraftRejected) as excinfo:
        save_draft(
            seeded,
            workflow_name="chat",
            yaml_text=yaml_text,
            change_note="broken",
            actor_user_id="admin-1",
            now=NOW,
        )

    assert excinfo.value.field.startswith(expected_field)
    assert seeded.query(WorkflowVersion).filter_by(workflow_name="chat").count() == 1


@pytest.mark.unit
def test_chat_draft_may_start_with_a_route_step(seeded):
    """Issue #85: the output guardrail now protects every prompt in a
    workflow (WorkflowDef.guarded_prompt_text), so `chat` no longer needs a
    single `agent` entry step to be safe to run."""
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=TRIAGE_BUILTIN.replace("name: triage", "name: chat"),
        change_note="route first",
        actor_user_id="admin-1",
        now=NOW,
    )

    assert draft.sequence == 2


@pytest.mark.unit
def test_save_draft_rejects_yaml_over_the_size_ceiling(seeded):
    oversized = CHAT_BUILTIN + "# " + "x" * MAX_WORKFLOW_YAML_BYTES + "\n"

    with pytest.raises(WorkflowDraftRejected) as excinfo:
        save_draft(
            seeded,
            workflow_name="chat",
            yaml_text=oversized,
            change_note="big",
            actor_user_id="admin-1",
            now=NOW,
        )

    assert excinfo.value.field == "yaml_text"


@pytest.mark.unit
@pytest.mark.parametrize("note", ["", "   "])
def test_save_draft_requires_a_change_note(seeded, note):
    with pytest.raises(WorkflowDraftRejected) as excinfo:
        save_draft(
            seeded,
            workflow_name="chat",
            yaml_text=CHAT_EDITED,
            change_note=note,
            actor_user_id="admin-1",
            now=NOW,
        )

    assert excinfo.value.field == "change_note"


@pytest.mark.unit
def test_save_draft_for_an_unknown_workflow_is_not_found(seeded):
    with pytest.raises(WorkflowNotFound):
        save_draft(
            seeded,
            workflow_name="brand_new",
            yaml_text=CHAT_EDITED,
            change_note="new",
            actor_user_id="admin-1",
            now=NOW,
        )


# --- publish / rollback --------------------------------------------------


@pytest.mark.unit
def test_publish_moves_the_pointer_and_records_old_and_new_version(seeded):
    builtin_id = _active_version_id(seeded)
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )

    publish(seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW)

    assert _active_version_id(seeded) == draft.id
    entry = AuditLogRepository(seeded).list_recent()[0]
    assert (entry.action, entry.old_value, entry.new_value) == (
        "workflow.published",
        builtin_id,
        draft.id,
    )


@pytest.mark.unit
def test_publish_rolls_back_the_pointer_if_the_audit_write_fails(seeded, monkeypatch):
    """Pointer move and audit entry are one transaction: an unaudited
    publish must not be able to happen."""
    builtin_id = _active_version_id(seeded)
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )
    seeded.commit()

    def failing_record(self, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(AuditLogRepository, "record", failing_record)
    with pytest.raises(RuntimeError):
        publish(seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW)
    seeded.rollback()

    assert _active_version_id(seeded) == builtin_id


@pytest.mark.unit
def test_publish_rejects_a_version_belonging_to_another_workflow(seeded):
    triage_version = WorkflowVersionRepository(seeded).latest_for_workflow("triage")

    with pytest.raises(WorkflowVersionNotFound):
        publish(
            seeded,
            workflow_name="chat",
            version_id=triage_version.id,
            actor_user_id="admin-1",
            now=NOW,
        )


@pytest.mark.unit
def test_rollback_republishes_an_older_version_as_its_own_audit_event(seeded):
    builtin_id = _active_version_id(seeded)
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )
    publish(seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW)

    rollback(seeded, workflow_name="chat", version_id=builtin_id, actor_user_id="admin-2", now=NOW)

    assert _active_version_id(seeded) == builtin_id
    entry = AuditLogRepository(seeded).list_recent()[0]
    assert (entry.action, entry.actor_user_id, entry.old_value, entry.new_value) == (
        "workflow.rolled_back",
        "admin-2",
        draft.id,
        builtin_id,
    )


@pytest.mark.unit
def test_rollback_only_targets_an_older_version(seeded):
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )

    with pytest.raises(WorkflowDraftRejected) as excinfo:
        rollback(
            seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW
        )

    assert excinfo.value.field == "version_id"


# --- runtime resolution --------------------------------------------------


@pytest.mark.unit
def test_resolve_active_workflow_serves_the_published_admin_version(seeded):
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )
    publish(seeded, workflow_name="chat", version_id=draft.id, actor_user_id="admin-1", now=NOW)

    active = resolve_active_workflow(seeded, "chat", now=NOW)

    assert active.version_id == draft.id
    assert active.agent_definition.system_prompt == "You are helpful and terse."


@pytest.mark.unit
def test_resolve_active_workflow_seeds_the_builtin_when_the_store_is_empty(db_session, monkeypatch):
    """A fresh database (or a unit test that never ran app startup) still
    gets a real, recorded version ID for every chat turn."""
    monkeypatch.setattr(workflow_service, "load_builtin_sources", lambda: {"chat": CHAT_BUILTIN})

    active = resolve_active_workflow(db_session, "chat", now=NOW)

    assert active.version_id == _active_version_id(db_session)
    assert active.agent_definition.system_prompt == "You are helpful."


# --- read-side helpers ---------------------------------------------------


@pytest.mark.unit
def test_list_workflows_reports_source_and_active_sequence(seeded):
    summaries = {s.name: s for s in list_workflows(seeded)}

    assert set(summaries) == {"chat", "triage"}
    assert summaries["chat"].active_version_sequence == 1
    assert summaries["chat"].active_version_source == "builtin"
    assert summaries["chat"].builtin_update_available is False


@pytest.mark.unit
def test_diff_versions_is_a_unified_diff_of_the_yaml(seeded):
    builtin = WorkflowVersionRepository(seeded).latest_for_workflow("chat")
    draft = save_draft(
        seeded,
        workflow_name="chat",
        yaml_text=CHAT_EDITED,
        change_note="terser",
        actor_user_id="admin-1",
        now=NOW,
    )

    diff = diff_versions(builtin, draft)

    assert "-    prompt: You are helpful.\n" in diff
    assert "+    prompt: You are helpful and terse.\n" in diff


@pytest.mark.unit
def test_workflow_graph_lists_steps_and_labelled_route_edges(seeded):
    triage = WorkflowVersionRepository(seeded).latest_for_workflow("triage")

    graph = workflow_graph(triage)

    assert graph["entry"] == "classify"
    assert {(n["id"], n["type"]) for n in graph["nodes"]} == {
        ("classify", "route"),
        ("answer", "agent"),
    }
    assert graph["edges"] == [{"source": "classify", "target": "answer", "label": "general"}]


# --- new workflows -------------------------------------------------------

NEW_WORKFLOW = (
    "name: summarizer\nversion: 1\nentry: summarize\nsteps:\n"
    "  summarize:\n    type: agent\n    prompt: Summarize the request in one line.\n"
)


@pytest.mark.unit
def test_create_workflow_stores_an_unpublished_first_version(seeded):
    version = workflow_service.create_workflow(
        seeded,
        yaml_text=NEW_WORKFLOW,
        change_note="new summarizer",
        actor_user_id="admin-1",
        now=NOW,
    )

    assert (version.workflow_name, version.sequence, version.source) == ("summarizer", 1, "admin")
    summary = next(s for s in list_workflows(seeded) if s.name == "summarizer")
    assert summary.active_version_id is None
    assert AuditLogRepository(seeded).list_recent()[0].action == "workflow.created"


@pytest.mark.unit
def test_create_workflow_refuses_an_existing_name(seeded):
    with pytest.raises(workflow_service.WorkflowAlreadyExists):
        workflow_service.create_workflow(
            seeded,
            yaml_text=CHAT_EDITED,
            change_note="dup",
            actor_user_id="admin-1",
            now=NOW,
        )


@pytest.mark.unit
def test_create_workflow_validates_like_a_draft(seeded):
    with pytest.raises(WorkflowDraftRejected) as excinfo:
        workflow_service.create_workflow(
            seeded,
            yaml_text=NEW_WORKFLOW.replace("entry: summarize", "entry: nope"),
            change_note="broken",
            actor_user_id="admin-1",
            now=NOW,
        )

    assert excinfo.value.field == "entry"
