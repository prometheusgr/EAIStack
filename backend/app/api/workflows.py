"""Admin endpoints for the versioned workflow store (issue #83).

Admin feature: every route depends on require_admin. Backs the Workflows
screen - list, history, detail, diff, diagram, create, save draft,
publish, rollback, test chat against any version, and eval runs of a
version's test suite (issue #84). All
business rules live in app.services.workflow_service,
app.services.chat_turn_service and app.services.workflow_eval_service
(eval runs of a version's test suite); this module maps them to HTTP.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.chat_http import refused_admission_response, reply_fields
from app.api.schemas import (
    EvalCaseRunResult,
    EvalRunDetail,
    EvalRunListResponse,
    EvalRunSummary,
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
    EvalRunInProgress,
    ThreadRepository,
    WorkflowActiveVersionRepository,
    WorkflowVersionRepository,
)
from app.services import workflow_eval_service, workflow_service
from app.services.chat_turn_service import admit_chat_message, run_chat_turn
from app.services.workflow_eval_service import (
    EvalRunNotFound,
    EvalRunNotRunning,
    EvalRunReport,
    NoTestCases,
    NotEvalRunOwner,
)
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


# --- eval runs (issue #84 slice B) --------------------------------------------
#
# The admin's page drives a run: start it, then advance it one case run per
# request until it ends - see app.services.workflow_eval_service for why.


@router.post(
    "/{workflow_name}/versions/{version_id}/eval-runs", response_model=None, status_code=201
)
async def start_eval_run(
    workflow_name: str,
    version_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EvalRunDetail | JSONResponse:
    """Start an eval run of a version's test suite. Nothing runs yet."""
    try:
        report = workflow_eval_service.start_eval_run(
            db, workflow_name, version_id, user_id=user["user_id"], now=utc_now()
        )
    except WorkflowVersionNotFound:
        return _not_found(f"No version {version_id!r} of {workflow_name!r}.")
    except WorkflowDraftRejected as exc:
        return _rejected(exc)
    except NoTestCases:
        return _eval_error(
            400, "no_test_cases", "This version declares no test cases under `tests:`."
        )
    except EvalRunInProgress:
        return _eval_error(
            409,
            "eval_run_in_progress",
            "Another eval run is in progress. Only one runs at a time, since eval "
            "runs share the model with production chat.",
        )
    return _eval_run_detail(report)


@router.get("/{workflow_name}/eval-runs", response_model=EvalRunListResponse)
async def list_eval_runs(
    workflow_name: str,
    version_id: str | None = None,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Eval runs of a workflow (optionally of one version), newest first."""
    runs = workflow_eval_service.list_eval_runs(db, workflow_name, version_id=version_id)
    return EvalRunListResponse(runs=[EvalRunSummary.model_validate(run) for run in runs])


@router.get("/{workflow_name}/eval-runs/{run_id}", response_model=None)
async def get_eval_run(
    workflow_name: str,
    run_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EvalRunDetail | JSONResponse:
    """One eval run with every case's pass rate and per-run checks."""
    try:
        report = workflow_eval_service.get_eval_run_report(db, workflow_name, run_id)
    except EvalRunNotFound:
        return _not_found(f"No eval run {run_id!r} of {workflow_name!r}.")
    return _eval_run_detail(report)


@router.post("/{workflow_name}/eval-runs/{run_id}/advance", response_model=None)
async def advance_eval_run(
    workflow_name: str,
    run_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EvalRunDetail | JSONResponse:
    """Execute the run's next case run and return the updated run."""
    try:
        report = await workflow_eval_service.advance_eval_run(
            db, workflow_name, run_id, user=user, clock=utc_now
        )
    except EvalRunNotFound:
        return _not_found(f"No eval run {run_id!r} of {workflow_name!r}.")
    except EvalRunNotRunning:
        return _eval_error(409, "eval_run_not_running", "This eval run has already ended.")
    except NotEvalRunOwner:
        return _eval_error(
            403, "eval_run_not_yours", "Only the admin who started an eval run can run it."
        )
    except WorkflowDraftRejected as exc:
        return _rejected(exc)
    return _eval_run_detail(report)


@router.post("/{workflow_name}/eval-runs/{run_id}/cancel", response_model=None)
async def cancel_eval_run(
    workflow_name: str,
    run_id: str,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> EvalRunDetail | JSONResponse:
    """Stop a running eval run, keeping the results recorded so far."""
    try:
        report = workflow_eval_service.cancel_eval_run(db, workflow_name, run_id, now=utc_now())
    except EvalRunNotFound:
        return _not_found(f"No eval run {run_id!r} of {workflow_name!r}.")
    return _eval_run_detail(report)


def _eval_error(status_code: int, detail: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "message": message})


def _eval_run_detail(report: EvalRunReport) -> EvalRunDetail:
    return EvalRunDetail.model_validate(
        {
            **EvalRunSummary.model_validate(report.run).model_dump(),
            "version_sequence": report.version_sequence,
            "cases": [
                {
                    "name": case_report.case.name,
                    "runs": case_report.case.runs,
                    "required_passes": case_report.case.required_passes(),
                    "runs_done": len(case_report.results),
                    "passes": case_report.passes,
                    "passed": case_report.passed,
                    "results": [
                        EvalCaseRunResult.model_validate(result) for result in case_report.results
                    ],
                }
                for case_report in report.cases
            ],
        }
    )
