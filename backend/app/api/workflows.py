"""Admin endpoints for the versioned workflow store (issue #83).

Admin feature: every route depends on require_admin. Backs the Workflows
screen - list, history, detail, diff, diagram, create, save draft,
publish, rollback, and test-chat against any version (issue #84). All business rules live in
app.services.workflow_service; this module maps them to HTTP.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.chat_http import refused_admission_response, reply_fields
from app.api.schemas import (
    PublishWorkflowRequest,
    SaveWorkflowDraftRequest,
    TestChatRequest,
    TestChatResponse,
    WorkflowDiffResponse,
    WorkflowListResponse,
    WorkflowSummaryResponse,
    WorkflowVersionDetail,
    WorkflowVersionListResponse,
    WorkflowVersionSummary,
)
from app.core.auth import require_admin
from app.db.database import get_db
from app.db.models import WorkflowVersion, utc_now
from app.repositories import (
    ThreadRepository,
    WorkflowActiveVersionRepository,
    WorkflowVersionRepository,
)
from app.services import workflow_service
from app.services.chat_turn_service import admit_chat_message, run_chat_turn
from app.services.workflow_service import (
    WorkflowAlreadyExists,
    WorkflowDraftRejected,
    WorkflowNotFound,
    WorkflowVersionNotFound,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _rejected(exc: WorkflowDraftRejected) -> JSONResponse:
    """422 naming the offending field, so the editor can show it inline.

    message always leads with the field: the frontend's error object only
    carries `message` (see frontend/src/api/authorizedFetch.ts), and an
    admin needs to know where in the YAML the problem is.
    """
    message = exc.message if exc.message.startswith(exc.field) else f"{exc.field}: {exc.message}"
    return JSONResponse(
        status_code=422,
        content={"detail": "workflow_draft_rejected", "field": exc.field, "message": message},
    )


def _not_found(message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "not_found", "message": message})


def _detail(version: WorkflowVersion, active_id: str | None) -> WorkflowVersionDetail:
    return WorkflowVersionDetail.model_validate(
        {
            **_summary_fields(version),
            "is_active": version.id == active_id,
            "yaml_text": version.yaml_text,
        }
    )


def _summary_fields(version: WorkflowVersion) -> dict:
    return {
        "id": version.id,
        "workflow_name": version.workflow_name,
        "sequence": version.sequence,
        "source": version.source,
        "author_user_id": version.author_user_id,
        "change_note": version.change_note,
        "content_hash": version.content_hash,
        "parent_version_id": version.parent_version_id,
        "created_at": version.created_at,
    }


def _active_id(db: Session, workflow_name: str) -> str | None:
    return WorkflowActiveVersionRepository(db).get_active_version_id(workflow_name)


@router.get("", response_model=WorkflowListResponse)
async def list_workflows(
    user: dict = Depends(require_admin), db: Session = Depends(get_db)
) -> WorkflowListResponse:
    """Every workflow, with its active version and update status."""
    return WorkflowListResponse(
        change_management_mode=workflow_service.CHANGE_MANAGEMENT_MODE,
        workflows=[
            WorkflowSummaryResponse(**summary.__dict__)
            for summary in workflow_service.list_workflows(db)
        ],
    )


@router.post("", response_model=None, status_code=201)
async def create_workflow(
    payload: SaveWorkflowDraftRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new workflow; its name comes from the YAML. Unpublished."""
    try:
        version = workflow_service.create_workflow(
            db,
            yaml_text=payload.yaml_text,
            change_note=payload.change_note,
            actor_user_id=user["user_id"],
            now=utc_now(),
        )
    except WorkflowDraftRejected as exc:
        return _rejected(exc)
    except WorkflowAlreadyExists as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "workflow_exists",
                "message": f"A workflow named {exc} already exists; edit it instead.",
            },
        )
    db.commit()
    return JSONResponse(
        status_code=201, content=_detail(version, active_id=None).model_dump(mode="json")
    )


@router.get("/{workflow_name}/versions", response_model=WorkflowVersionListResponse)
async def list_versions(
    workflow_name: str, user: dict = Depends(require_admin), db: Session = Depends(get_db)
):
    """A workflow's history, newest first, marking the active version."""
    versions = WorkflowVersionRepository(db).list_for_workflow(workflow_name)
    if not versions:
        return _not_found(f"No workflow named {workflow_name!r}.")
    active_id = _active_id(db, workflow_name)
    return WorkflowVersionListResponse(
        versions=[
            WorkflowVersionSummary(**_summary_fields(v), is_active=v.id == active_id)
            for v in versions
        ]
    )


@router.post("/{workflow_name}/versions", response_model=None, status_code=201)
async def save_draft(
    workflow_name: str,
    payload: SaveWorkflowDraftRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Validate and save a new unpublished version."""
    try:
        version = workflow_service.save_draft(
            db,
            workflow_name=workflow_name,
            yaml_text=payload.yaml_text,
            change_note=payload.change_note,
            actor_user_id=user["user_id"],
            now=utc_now(),
        )
    except WorkflowDraftRejected as exc:
        return _rejected(exc)
    except WorkflowNotFound:
        return _not_found(f"No workflow named {workflow_name!r}.")
    db.commit()
    return JSONResponse(
        status_code=201,
        content=_detail(version, _active_id(db, workflow_name)).model_dump(mode="json"),
    )


@router.get("/{workflow_name}/versions/{version_id}", response_model=WorkflowVersionDetail)
async def get_version(
    workflow_name: str,
    version_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """One version, including its YAML."""
    try:
        version = workflow_service.get_version(db, workflow_name, version_id)
    except WorkflowVersionNotFound:
        return _not_found(f"No version {version_id!r} of {workflow_name!r}.")
    return _detail(version, _active_id(db, workflow_name))


@router.get("/{workflow_name}/versions/{version_id}/graph", response_model=None)
async def get_version_graph(
    workflow_name: str,
    version_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """A version's step graph (nodes and edges) for the diagram."""
    try:
        version = workflow_service.get_version(db, workflow_name, version_id)
    except WorkflowVersionNotFound:
        return _not_found(f"No version {version_id!r} of {workflow_name!r}.")
    return workflow_service.workflow_graph(version)


@router.post("/{workflow_name}/versions/{version_id}/test-chat", response_model=None)
async def test_chat(
    workflow_name: str,
    version_id: str,
    request: TestChatRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TestChatResponse | JSONResponse:
    """Run one chat turn against any saved version, typically a draft.

    Never publishes anything: production chat keeps running the published
    version. Runs under production's exact rules - shared rate-limit
    bucket, both guardrails (the leak guard checks the draft's own
    prompts), real tools - via app.services.chat_turn_service. The
    conversation is a test thread bound to this version, kept out of every
    production thread lookup, and each turn is recorded as a test run.
    """
    try:
        workflow = workflow_service.resolve_version_for_test(db, workflow_name, version_id)
    except WorkflowVersionNotFound:
        return _not_found(f"No version {version_id!r} of {workflow_name!r}.")
    except WorkflowDraftRejected as exc:
        return _rejected(exc)

    admission = admit_chat_message(
        db, user_id=user["user_id"], message=request.message, now=utc_now()
    )
    if not admission.admitted:
        db.commit()  # a guardrail rejection's audit entry
        return refused_admission_response(admission)

    thread = ThreadRepository(db).get_or_create_test_thread(
        request.thread_id,
        user["user_id"],
        workflow_name=workflow_name,
        version_id=workflow.version_id,
    )
    outcome = await run_chat_turn(
        db,
        user=user,
        thread=thread,
        workflow=workflow,
        message=request.message,
        guardrail_config=admission.guardrail_config,
        run_kind="test",
        now=utc_now(),
    )
    return TestChatResponse(
        **reply_fields(outcome),
        workflow=workflow_name,
        test_version_id=workflow.version_id,
        test_version_sequence=workflow.version_sequence,
    )


@router.get("/{workflow_name}/diff", response_model=WorkflowDiffResponse)
async def diff(
    workflow_name: str,
    from_version: str,
    to_version: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Unified diff between any two versions of one workflow."""
    try:
        older = workflow_service.get_version(db, workflow_name, from_version)
        newer = workflow_service.get_version(db, workflow_name, to_version)
    except WorkflowVersionNotFound as exc:
        return _not_found(f"No version {exc} of {workflow_name!r}.")
    return WorkflowDiffResponse(diff=workflow_service.diff_versions(older, newer))


@router.post("/{workflow_name}/publish", response_model=WorkflowVersionDetail)
async def publish(
    workflow_name: str,
    payload: PublishWorkflowRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Make a version live. Audited as workflow.published."""
    return _move_pointer(workflow_service.publish, workflow_name, payload, user, db)


@router.post("/{workflow_name}/rollback", response_model=WorkflowVersionDetail)
async def rollback(
    workflow_name: str,
    payload: PublishWorkflowRequest,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Re-publish an older version. Audited as workflow.rolled_back."""
    return _move_pointer(workflow_service.rollback, workflow_name, payload, user, db)


def _move_pointer(operation, workflow_name, payload, user, db):
    try:
        version = operation(
            db,
            workflow_name=workflow_name,
            version_id=payload.version_id,
            actor_user_id=user["user_id"],
            now=utc_now(),
        )
    except WorkflowVersionNotFound:
        return _not_found(f"No version {payload.version_id!r} of {workflow_name!r}.")
    except WorkflowDraftRejected as exc:
        return _rejected(exc)
    db.commit()
    return _detail(version, version.id)
