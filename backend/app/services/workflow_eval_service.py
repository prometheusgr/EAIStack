"""Eval runs: executing a workflow version's test suite (issue #84 slice B).

The admin's page drives a run one case run per request (start, then advance
until it ends) rather than the backend running it as a background task:
every case run forwards the admin's own Keycloak access token to tools such
as doc-search, which verifies it, and an access token outlives only a few
minutes - shorter than a suite on CPU inference. Each advance request
carries a token the frontend has just refreshed, exactly like test chat.

Each case run goes through app.services.chat_turn_service.run_chat_turn on
a fresh test thread bound to the version, so evals run under production's
guardrails, real tools and tracing. They skip the per-user chat rate limit
(a suite would throttle itself against the admin's own bucket); their cost
is bounded instead by the suite ceilings in app.workflows.schema and by one
executing run per deployment.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import WorkflowEvalCaseResult, WorkflowEvalRun
from app.guardrails.input_guardrail import GuardrailVerdict
from app.repositories import (
    ThreadRepository,
    WorkflowEvalCaseResultRepository,
    WorkflowEvalRunRepository,
)
from app.services import workflow_service
from app.services.chat_guardrail_service import check_input_guardrail
from app.services.chat_turn_service import run_chat_turn
from app.services.eval_config_service import resolve_eval_config
from app.services.guardrail_config_service import resolve_guardrail_config
from app.services.workflow_service import ResolvedWorkflow
from app.workflows.eval_scoring import (
    CaseRunObservation,
    case_passed,
    run_passed,
    score_case_run,
)
from app.workflows.schema import EvalCaseDef

logger = logging.getLogger(__name__)

# How long past the case-run timeout a running eval may go without a request
# before it counts as abandoned (its page was closed without cancelling).
# Covers network and scheduling slack between two advance requests - an
# implementation margin, not something an operator would tune.
EVAL_RUN_ABANDON_GRACE = timedelta(seconds=60)


class NoTestCases(Exception):
    """The version declares no test cases, so there is nothing to run."""


class EvalRunNotFound(Exception):
    pass


class EvalRunNotRunning(Exception):
    """The run already ended (completed, cancelled or abandoned)."""


class NotEvalRunOwner(Exception):
    """Only the admin who started a run drives it: each case run forwards
    that admin's own token to tools and is attributed to them."""


@dataclass(frozen=True)
class CaseReport:
    """One test case's progress and verdict within an eval run."""

    case: EvalCaseDef
    results: list[WorkflowEvalCaseResult]

    @property
    def passes(self) -> int:
        return sum(1 for result in self.results if result.passed)

    @property
    def passed(self) -> bool | None:
        """None until every run of the case has been recorded."""
        if len(self.results) < self.case.runs:
            return None
        return case_passed(self.case, (result.passed for result in self.results))


@dataclass(frozen=True)
class EvalRunReport:
    run: WorkflowEvalRun
    version_sequence: int
    cases: list[CaseReport]


def start_eval_run(
    db: Session, workflow_name: str, version_id: str, *, user_id: str, now: datetime
) -> EvalRunReport:
    """Record a new running eval run of version_id's suite and commit.

    First expires a run whose page went quiet for longer than any case run
    may take, so a closed page never holds the slot forever. Raises
    WorkflowVersionNotFound, WorkflowDraftRejected, NoTestCases or
    EvalRunInProgress.
    """
    workflow = workflow_service.resolve_version_for_test(db, workflow_name, version_id)
    suite = workflow.definition.tests
    if not suite:
        raise NoTestCases()

    runs = WorkflowEvalRunRepository(db)
    timeout = timedelta(seconds=resolve_eval_config(db).case_run_timeout_seconds)
    runs.expire_abandoned(idle_before=now - timeout - EVAL_RUN_ABANDON_GRACE, now=now)
    run = runs.start(
        workflow_name=workflow_name,
        workflow_version_id=version_id,
        case_runs_total=sum(case.runs for case in suite),
        started_by_user_id=user_id,
        now=now,
    )
    db.commit()
    return _report(db, run, workflow)


async def advance_eval_run(
    db: Session,
    workflow_name: str,
    run_id: str,
    *,
    user: dict,
    clock: Callable[[], datetime],
) -> EvalRunReport:
    """Execute the run's next pending case run, score and record it, and
    finish the run once every case run is recorded. Commits.

    clock rather than a single `now`: a case run can take minutes, and the
    activity and finish times must reflect when things actually happened.
    Raises EvalRunNotFound, EvalRunNotRunning or NotEvalRunOwner.
    """
    run = _get_run(db, workflow_name, run_id)
    if run.status != "running":
        raise EvalRunNotRunning()
    if run.started_by_user_id != user["user_id"]:
        raise NotEvalRunOwner()

    workflow = workflow_service.resolve_version_for_test(db, workflow_name, run.workflow_version_id)
    pending = _next_pending_case_run(db, run, workflow)
    if pending is None:
        _finish_if_complete(db, run, workflow, now=clock())
        db.commit()
        return _report(db, run, workflow)

    case, run_index = pending
    runs = WorkflowEvalRunRepository(db)
    runs.touch(run.id, now=clock())
    db.commit()

    started = time.monotonic()
    observation, thread_id = await _execute_case_run(db, workflow, case, run, user, clock)
    checks = score_case_run(case, workflow.definition, observation)
    try:
        WorkflowEvalCaseResultRepository(db).record(
            eval_run_id=run.id,
            case_name=case.name,
            run_index=run_index,
            outcome=observation.outcome,
            passed=run_passed(checks),
            checks=[
                {"check": c.check, "kind": c.kind, "passed": c.passed, "detail": c.detail}
                for c in checks
            ],
            thread_id=thread_id,
            duration_ms=int((time.monotonic() - started) * 1000),
            now=clock(),
        )
    except IntegrityError:
        # A concurrent advance of the same run recorded this case run first;
        # its result stands.
        db.rollback()
        return _report(db, run, workflow)
    runs.record_progress(run.id, now=clock())
    _finish_if_complete(db, run, workflow, now=clock())
    db.commit()
    return _report(db, run, workflow)


def cancel_eval_run(
    db: Session, workflow_name: str, run_id: str, *, now: datetime
) -> EvalRunReport:
    """Stop a running eval run, keeping the results recorded so far, and
    commit. Cancelling a run that already ended changes nothing."""
    run = _get_run(db, workflow_name, run_id)
    if run.status == "running":
        WorkflowEvalRunRepository(db).finish(run.id, status="cancelled", passed=None, now=now)
        db.commit()
    return get_eval_run_report(db, workflow_name, run_id)


def get_eval_run_report(db: Session, workflow_name: str, run_id: str) -> EvalRunReport:
    run = _get_run(db, workflow_name, run_id)
    workflow = workflow_service.resolve_version_for_test(db, workflow_name, run.workflow_version_id)
    return _report(db, run, workflow)


def list_eval_runs(
    db: Session, workflow_name: str, *, version_id: str | None
) -> list[WorkflowEvalRun]:
    return WorkflowEvalRunRepository(db).list_for_workflow(workflow_name, version_id=version_id)


async def _execute_case_run(
    db: Session,
    workflow: ResolvedWorkflow,
    case: EvalCaseDef,
    run: WorkflowEvalRun,
    user: dict,
    clock: Callable[[], datetime],
) -> tuple[CaseRunObservation, str | None]:
    """Run one case once and observe what happened.

    A model or tool failure is a result (outcome "error"), not a reason to
    abort the suite: an eval exists to measure exactly that kind of
    unreliability.
    """
    guardrail_config = resolve_guardrail_config(db)
    verdict = check_input_guardrail(
        db,
        message=case.input,
        actor_user_id=user["user_id"],
        now=clock(),
        config=guardrail_config,
    )
    if verdict.verdict == GuardrailVerdict.REJECTED:
        db.commit()  # the rejection's audit entry, as for any other message
        return CaseRunObservation(outcome="rejected_by_input_guardrail"), None

    thread = ThreadRepository(db).get_or_create_test_thread(
        None, user["user_id"], workflow_name=workflow.workflow_name, version_id=workflow.version_id
    )
    db.commit()
    timeout_seconds = resolve_eval_config(db).case_run_timeout_seconds
    try:
        outcome = await asyncio.wait_for(
            run_chat_turn(
                db,
                user=user,
                thread=thread,
                workflow=workflow,
                message=case.input,
                guardrail_config=guardrail_config,
                run_kind="eval",
                now=clock(),
                eval_run_id=run.id,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        db.rollback()
        return CaseRunObservation(outcome="timed_out"), thread.id
    except Exception:
        logger.exception("Eval run %s: case %r failed", run.id, case.name)
        db.rollback()
        return CaseRunObservation(outcome="error"), thread.id

    return (
        CaseRunObservation(
            outcome="completed",
            reply=outcome.text,
            step_outputs=outcome.step_outputs,
            tools_called=outcome.tools_called,
        ),
        thread.id,
    )


def _next_pending_case_run(
    db: Session, run: WorkflowEvalRun, workflow: ResolvedWorkflow
) -> tuple[EvalCaseDef, int] | None:
    """The first (case, run index), in suite order, not yet recorded."""
    recorded = {
        (result.case_name, result.run_index)
        for result in WorkflowEvalCaseResultRepository(db).list_for_run(run.id)
    }
    for case in workflow.definition.tests:
        for run_index in range(case.runs):
            if (case.name, run_index) not in recorded:
                return case, run_index
    return None


def _finish_if_complete(
    db: Session, run: WorkflowEvalRun, workflow: ResolvedWorkflow, *, now: datetime
) -> None:
    # A case run takes minutes; the admin may have cancelled (or a newer
    # start abandoned) the run meanwhile, and that must stand.
    db.refresh(run, attribute_names=["status"])
    if run.status != "running" or run.case_runs_done < run.case_runs_total:
        return
    cases = _report(db, run, workflow).cases
    WorkflowEvalRunRepository(db).finish(
        run.id,
        status="completed",
        passed=all(case.passed for case in cases),
        now=now,
    )


def _report(db: Session, run: WorkflowEvalRun, workflow: ResolvedWorkflow) -> EvalRunReport:
    results = WorkflowEvalCaseResultRepository(db).list_for_run(run.id)
    return EvalRunReport(
        run=run,
        version_sequence=workflow.version_sequence,
        cases=[
            CaseReport(
                case=case,
                results=sorted(
                    (result for result in results if result.case_name == case.name),
                    key=lambda result: result.run_index,
                ),
            )
            for case in workflow.definition.tests
        ],
    )


def _get_run(db: Session, workflow_name: str, run_id: str) -> WorkflowEvalRun:
    run = WorkflowEvalRunRepository(db).get(run_id)
    if run is None or run.workflow_name != workflow_name:
        raise EvalRunNotFound()
    return run
