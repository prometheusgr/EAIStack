"""Workflow change management: drafts, publish, rollback (issue #83).

Postgres is the system of record for workflows (epic #80). The built-in
YAML files shipped in the image are recorded as versions too, so every
workflow - built-in or admin-edited - has one history, one active-version
pointer, and one audit trail.

Change-management mode is `direct` (publish from the Workflows screen)
and only `direct`: issue #87 adds git-backed modes and two-person
approval. Every pointer move goes through _apply_publish, the single
step those modes will replace, rather than a mode abstraction built
before a second mode exists.

None of these functions commit; the caller owns the transaction, so a
pointer move and its audit entry always land (or roll back) together.
Time is injected as `now` throughout.
"""

import difflib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import yaml

from app.agents.registry import AgentDefinition, build_agent_definition
from app.core.config import settings
from app.db.models import WorkflowVersion
from app.repositories import (
    AuditLogRepository,
    WorkflowActiveVersionRepository,
    WorkflowVersionRepository,
)
from app.workflows.loader import load_workflow_sources
from app.workflows.schema import (
    AgentStepDef,
    RouteStepDef,
    WorkflowDef,
    WorkflowValidationError,
    parse_workflow_definition,
)

# Fixed constants, deliberately not admin settings (AGENTS.md
# configuration call-out). The size ceiling bounds what a single save can
# store and parse; making it DB-editable would let the admins it constrains
# raise it, the same reasoning as REVIEW_LOOP_MAX_ITERATIONS_CEILING.
MAX_WORKFLOW_YAML_BYTES = 64 * 1024
MAX_CHANGE_NOTE_CHARS = 2000

# Issue #87 makes this env/Helm deployment config; today `direct` is the
# only mode that exists, so it is a constant shown read-only in the UI.
CHANGE_MANAGEMENT_MODE = "direct"

# The workflow a conversation uses when the user doesn't choose one
# (issue #85): today's behavior for everyone who never opens the picker.
DEFAULT_WORKFLOW = "chat"

SYSTEM_ACTOR = "system"


class WorkflowDraftRejected(Exception):
    """A draft (or publish/rollback request) failed validation.

    field names what is wrong ("yaml", "entry", "steps.respond.tools",
    "change_note", ...) so the admin UI can show the error next to it.
    """

    def __init__(self, *, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class WorkflowNotFound(Exception):
    """No workflow by that name exists in the store."""


class WorkflowVersionNotFound(Exception):
    """No version by that ID exists for the named workflow."""


class WorkflowAlreadyExists(Exception):
    """create_workflow was given a name that already has versions."""


@dataclass(frozen=True)
class ResolvedWorkflow:
    """One recorded version of a workflow, ready for an endpoint to run:
    the published one for production chat, any saved one for test chat."""

    workflow_name: str
    version_id: str
    version_sequence: int
    agent_definition: AgentDefinition


@dataclass(frozen=True)
class AvailableWorkflow:
    """A published workflow an end user can start a conversation with."""

    name: str
    description: str
    is_default: bool


@dataclass(frozen=True)
class WorkflowSummary:
    """One row of the Workflows screen's list."""

    name: str
    active_version_id: str | None
    active_version_sequence: int | None
    active_version_source: str | None
    latest_version_sequence: int
    builtin_update_available: bool


def load_builtin_sources() -> dict[str, str]:
    """The shipped built-in workflow files, as name -> exact YAML text."""
    return load_workflow_sources(settings.workflow_definitions_dir)


def parse_draft_yaml(workflow_name: str, yaml_text: str) -> WorkflowDef:
    """Validate draft YAML for workflow_name with the same rules as a
    built-in file at startup, plus the checks that only apply to edits.

    Raises WorkflowDraftRejected naming the offending field.
    """
    definition = _parse_yaml_definition(yaml_text, source_label=f"{workflow_name} (draft)")
    if definition.name != workflow_name:
        raise WorkflowDraftRejected(
            field="name",
            message=f"name must stay {workflow_name!r}; renaming a workflow is not supported.",
        )
    return definition


def _parse_yaml_definition(yaml_text: str, *, source_label: str) -> WorkflowDef:
    """Size-check, YAML-parse and schema-validate one definition."""
    if len(yaml_text.encode("utf-8")) > MAX_WORKFLOW_YAML_BYTES:
        raise WorkflowDraftRejected(
            field="yaml_text",
            message=f"Workflow YAML must be at most {MAX_WORKFLOW_YAML_BYTES} bytes.",
        )
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise WorkflowDraftRejected(field="yaml", message=f"Not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowDraftRejected(
            field="<root>", message="A workflow definition must be a YAML mapping."
        )

    try:
        return parse_workflow_definition(raw, source_file=source_label)
    except WorkflowValidationError as exc:
        raise WorkflowDraftRejected(field=exc.field, message=exc.message) from exc


def sync_builtin_versions(db, builtin_sources: dict[str, str], *, now: datetime) -> None:
    """Record each shipped built-in as a version if its text changed, and
    make it active unless an admin version is currently published.

    Called at startup. A built-in whose text matches its latest recorded
    built-in version is left alone, so restarts are no-ops. A changed
    built-in becomes active only when the active version is itself a
    built-in (no admin change to protect); otherwise it is recorded and
    reported as an available update (epic #80 invariant 4).
    """
    versions = WorkflowVersionRepository(db)
    pointers = WorkflowActiveVersionRepository(db)

    for name, yaml_text in builtin_sources.items():
        latest_builtin = versions.latest_builtin_for_workflow(name)
        if latest_builtin is not None and latest_builtin.yaml_text == yaml_text:
            continue

        active_id = pointers.get_active_version_id(name)
        active = versions.get(active_id) if active_id else None
        new_builtin = versions.add(
            workflow_name=name,
            yaml_text=yaml_text,
            source="builtin",
            author_user_id=SYSTEM_ACTOR,
            change_note="Built-in definition shipped with this release.",
            parent_version_id=latest_builtin.id if latest_builtin else None,
            now=now,
        )
        if active is None or active.source == "builtin":
            _apply_publish(
                db,
                workflow_name=name,
                version=new_builtin,
                previous_version_id=active_id,
                action="workflow.builtin_synced",
                actor_user_id=SYSTEM_ACTOR,
                now=now,
            )


def save_draft(
    db,
    *,
    workflow_name: str,
    yaml_text: str,
    change_note: str,
    actor_user_id: str,
    now: datetime,
) -> WorkflowVersion:
    """Validate and store a new, unpublished admin version.

    Editing a built-in this way creates an admin-owned version parented on
    the currently active one; the built-in itself is never modified.
    """
    versions = WorkflowVersionRepository(db)
    if versions.latest_for_workflow(workflow_name) is None:
        raise WorkflowNotFound(workflow_name)

    note = _validated_change_note(change_note)
    parse_draft_yaml(workflow_name, yaml_text)

    parent_id = WorkflowActiveVersionRepository(db).get_active_version_id(workflow_name)
    draft = versions.add(
        workflow_name=workflow_name,
        yaml_text=yaml_text,
        source="admin",
        author_user_id=actor_user_id,
        change_note=note,
        parent_version_id=parent_id,
        now=now,
    )
    AuditLogRepository(db).record(
        actor_user_id=actor_user_id,
        action="workflow.draft_saved",
        field_name=workflow_name,
        old_value=parent_id,
        new_value=draft.id,
        now=now,
    )
    return draft


def create_workflow(
    db, *, yaml_text: str, change_note: str, actor_user_id: str, now: datetime
) -> WorkflowVersion:
    """Store the first version of a brand-new workflow, unpublished.

    The name comes from the YAML itself. A new workflow is not reachable
    from chat until workflow selection lands (issue #85); it can be
    drafted, published and versioned like any other.
    """
    definition = _parse_yaml_definition(yaml_text, source_label="new workflow")
    versions = WorkflowVersionRepository(db)
    if versions.latest_for_workflow(definition.name) is not None:
        raise WorkflowAlreadyExists(definition.name)
    note = _validated_change_note(change_note)
    # Run the name-specific checks too (e.g. a new "chat" can't happen
    # here since it exists, but the rule set stays in one place).
    parse_draft_yaml(definition.name, yaml_text)

    version = versions.add(
        workflow_name=definition.name,
        yaml_text=yaml_text,
        source="admin",
        author_user_id=actor_user_id,
        change_note=note,
        parent_version_id=None,
        now=now,
    )
    AuditLogRepository(db).record(
        actor_user_id=actor_user_id,
        action="workflow.created",
        field_name=definition.name,
        old_value=None,
        new_value=version.id,
        now=now,
    )
    return version


def _validated_change_note(change_note: str) -> str:
    note = change_note.strip()
    if not note:
        raise WorkflowDraftRejected(field="change_note", message="A change note is required.")
    if len(note) > MAX_CHANGE_NOTE_CHARS:
        raise WorkflowDraftRejected(
            field="change_note",
            message=f"A change note must be at most {MAX_CHANGE_NOTE_CHARS} characters.",
        )
    return note


def publish(
    db, *, workflow_name: str, version_id: str, actor_user_id: str, now: datetime
) -> WorkflowVersion:
    """Make version_id the active version of workflow_name."""
    version = _get_version_of(db, workflow_name, version_id)
    # Re-validated at publish time, not just at save: a version saved
    # before a later rule (or a tool's removal from the registry) would
    # otherwise reach the chat endpoint unchecked.
    parse_draft_yaml(workflow_name, version.yaml_text)
    previous_id = WorkflowActiveVersionRepository(db).get_active_version_id(workflow_name)
    _apply_publish(
        db,
        workflow_name=workflow_name,
        version=version,
        previous_version_id=previous_id,
        action="workflow.published",
        actor_user_id=actor_user_id,
        now=now,
    )
    return version


def rollback(
    db, *, workflow_name: str, version_id: str, actor_user_id: str, now: datetime
) -> WorkflowVersion:
    """Re-publish an older version. Recorded as its own audit action so
    the trail distinguishes "moved forward" from "backed out a change"."""
    version = _get_version_of(db, workflow_name, version_id)
    pointers = WorkflowActiveVersionRepository(db)
    previous_id = pointers.get_active_version_id(workflow_name)
    current = WorkflowVersionRepository(db).get(previous_id) if previous_id else None
    if current is None or version.sequence >= current.sequence:
        raise WorkflowDraftRejected(
            field="version_id",
            message="Rollback must target a version older than the active one; use publish instead.",
        )
    parse_draft_yaml(workflow_name, version.yaml_text)
    _apply_publish(
        db,
        workflow_name=workflow_name,
        version=version,
        previous_version_id=previous_id,
        action="workflow.rolled_back",
        actor_user_id=actor_user_id,
        now=now,
    )
    return version


def _apply_publish(
    db,
    *,
    workflow_name: str,
    version: WorkflowVersion,
    previous_version_id: str | None,
    action: str,
    actor_user_id: str,
    now: datetime,
) -> None:
    """Move the active pointer and audit it - the one publish step.

    Issue #87's change-management modes (git-advisory, git-authoritative,
    two-person approval) replace or gate this function; every path that
    changes which version is live goes through it.
    """
    WorkflowActiveVersionRepository(db).set_active(
        workflow_name=workflow_name, version_id=version.id, updated_by=actor_user_id, now=now
    )
    AuditLogRepository(db).record(
        actor_user_id=actor_user_id,
        action=action,
        field_name=workflow_name,
        old_value=previous_version_id,
        new_value=version.id,
        now=now,
    )


def resolve_active_workflow(db, workflow_name: str, *, now: datetime) -> ResolvedWorkflow:
    """The published version of workflow_name, compiled-ready.

    Normally the pointer was set at startup by sync_builtin_versions. If
    the store has no record of this workflow at all (a fresh database that
    hasn't seen a startup sync, e.g. under unit tests), the shipped
    built-ins are synced first, so every chat turn is still attributed to
    a real, recorded version rather than an anonymous in-memory one.
    """
    pointers = WorkflowActiveVersionRepository(db)
    active_id = pointers.get_active_version_id(workflow_name)
    if active_id is None:
        _ensure_builtins_recorded(db, now=now)
        active_id = pointers.get_active_version_id(workflow_name)
    if active_id is None:
        raise WorkflowNotFound(workflow_name)

    version = WorkflowVersionRepository(db).get(active_id)
    assert version is not None  # FK-guaranteed: the pointer references a stored version
    return _resolved(version, _parse_stored(version))


def resolve_version_for_test(db, workflow_name: str, version_id: str) -> ResolvedWorkflow:
    """Any saved version of workflow_name - typically an unpublished draft -
    for an admin's test chat (issue #84). Never changes what is published.

    Re-validated like publish, so a version saved before a later rule (or a
    tool's removal from the registry) can't run unchecked. Raises
    WorkflowVersionNotFound or WorkflowDraftRejected.
    """
    version = _get_version_of(db, workflow_name, version_id)
    return _resolved(version, parse_draft_yaml(workflow_name, version.yaml_text))


def _resolved(version: WorkflowVersion, definition: WorkflowDef) -> ResolvedWorkflow:
    return ResolvedWorkflow(
        workflow_name=version.workflow_name,
        version_id=version.id,
        version_sequence=version.sequence,
        agent_definition=build_agent_definition(version.workflow_name, definition),
    )


def list_available_workflows(db, *, now: datetime) -> list[AvailableWorkflow]:
    """Every workflow with a published version, default first, then by name.

    The user-facing list (issue #85): drafts and never-published workflows
    are excluded, since only a published version can run. In v1 every
    published workflow is offered to every signed-in user; restricting one
    to a role is a deliberate follow-up, not an oversight.
    """
    _ensure_builtins_recorded(db, now=now)
    versions = WorkflowVersionRepository(db)
    pointers = WorkflowActiveVersionRepository(db)
    available = []
    for name in versions.list_workflow_names():
        active_id = pointers.get_active_version_id(name)
        if active_id is None:
            continue
        version = versions.get(active_id)
        assert version is not None  # FK-guaranteed
        available.append(
            AvailableWorkflow(
                name=name,
                description=_parse_stored(version).description,
                is_default=name == DEFAULT_WORKFLOW,
            )
        )
    return sorted(available, key=lambda w: (not w.is_default, w.name))


def is_available(db, workflow_name: str, *, now: datetime) -> bool:
    """Whether workflow_name has a published version a conversation can use."""
    _ensure_builtins_recorded(db, now=now)
    return WorkflowActiveVersionRepository(db).get_active_version_id(workflow_name) is not None


def _ensure_builtins_recorded(db, *, now: datetime) -> None:
    """Sync the shipped built-ins if the store has never seen them (a fresh
    database that hasn't been through a startup sync, e.g. under unit tests).
    """
    if WorkflowVersionRepository(db).latest_for_workflow(DEFAULT_WORKFLOW) is None:
        sync_builtin_versions(db, load_builtin_sources(), now=now)


def _parse_stored(version: WorkflowVersion) -> WorkflowDef:
    """Parse a stored version's YAML (already validated when it was saved)."""
    return parse_workflow_definition(
        yaml.safe_load(version.yaml_text),
        source_file=f"{version.workflow_name} v{version.sequence}",
    )


def list_workflows(db) -> list[WorkflowSummary]:
    """Every workflow in the store, with its active and latest versions."""
    versions = WorkflowVersionRepository(db)
    pointers = WorkflowActiveVersionRepository(db)
    summaries = []
    for name in versions.list_workflow_names():
        latest = versions.latest_for_workflow(name)
        assert latest is not None  # list_workflow_names only returns names with a version
        active_id = pointers.get_active_version_id(name)
        active = versions.get(active_id) if active_id else None
        latest_builtin = versions.latest_builtin_for_workflow(name)
        summaries.append(
            WorkflowSummary(
                name=name,
                active_version_id=active.id if active else None,
                active_version_sequence=active.sequence if active else None,
                active_version_source=active.source if active else None,
                latest_version_sequence=latest.sequence,
                builtin_update_available=bool(
                    active is not None
                    and active.source == "admin"
                    and latest_builtin is not None
                    and latest_builtin.sequence > active.sequence
                ),
            )
        )
    return summaries


def get_version(db, workflow_name: str, version_id: str) -> WorkflowVersion:
    """One version of workflow_name, or WorkflowVersionNotFound."""
    return _get_version_of(db, workflow_name, version_id)


def diff_versions(from_version: WorkflowVersion, to_version: WorkflowVersion) -> str:
    """Unified diff of two versions' YAML, labelled with their sequence."""
    return "".join(
        difflib.unified_diff(
            from_version.yaml_text.splitlines(keepends=True),
            to_version.yaml_text.splitlines(keepends=True),
            fromfile=f"{from_version.workflow_name} v{from_version.sequence}",
            tofile=f"{to_version.workflow_name} v{to_version.sequence}",
        )
    )


def workflow_graph(version: WorkflowVersion) -> dict[str, Any]:
    """Nodes and edges of a version's step graph, for the admin diagram.

    Built from the validated definition rather than LangGraph's
    get_graph(): compiling needs a db session, caller token and MCP URL
    just to draw a picture, and the definition already holds every edge.
    """
    definition = _parse_stored(version)
    nodes = [{"id": name, "type": step.type} for name, step in definition.steps.items()]
    edges: list[dict[str, str | None]] = []
    for name, step in definition.steps.items():
        if isinstance(step, AgentStepDef) and step.next:
            edges.append({"source": name, "target": step.next, "label": None})
        elif isinstance(step, RouteStepDef):
            for label, target in step.branches.items():
                edges.append({"source": name, "target": target, "label": label})
    return {"entry": definition.entry, "nodes": nodes, "edges": edges}


def _get_version_of(db, workflow_name: str, version_id: str) -> WorkflowVersion:
    version = WorkflowVersionRepository(db).get(version_id)
    if version is None or version.workflow_name != workflow_name:
        raise WorkflowVersionNotFound(version_id)
    return version
