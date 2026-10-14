"""Repositories for workflow eval runs and their results (issue #84)."""

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import WorkflowEvalCaseResult, WorkflowEvalRun


class EvalRunInProgress(Exception):
    """Another eval run is already executing in this deployment."""


class WorkflowEvalRunRepository:
    """Eval-run job records: started, advanced, then finished."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def start(
        self,
        *,
        workflow_name: str,
        workflow_version_id: str,
        case_runs_total: int,
        started_by_user_id: str,
        now: datetime,
    ) -> WorkflowEvalRun:
        """Record a new running eval run. Does not commit.

        Raises EvalRunInProgress when another run holds the active slot
        (WorkflowEvalRun.active_slot's unique constraint), rolling back to
        the savepoint so the caller's session stays usable.
        """
        run = WorkflowEvalRun(
            workflow_name=workflow_name,
            workflow_version_id=workflow_version_id,
            status="running",
            case_runs_total=case_runs_total,
            case_runs_done=0,
            active_slot=True,
            started_by_user_id=started_by_user_id,
            started_at=now.replace(tzinfo=None),
            last_activity_at=now.replace(tzinfo=None),
        )
        try:
            with self.db.begin_nested():
                self.db.add(run)
        except IntegrityError as exc:
            raise EvalRunInProgress() from exc
        return run

    def get(self, run_id: str) -> WorkflowEvalRun | None:
        return self.db.get(WorkflowEvalRun, run_id)

    def list_for_workflow(
        self, workflow_name: str, *, version_id: str | None = None
    ) -> list[WorkflowEvalRun]:
        """Runs of workflow_name (optionally of one version), newest first."""
        query = self.db.query(WorkflowEvalRun).filter(
            WorkflowEvalRun.workflow_name == workflow_name
        )
        if version_id is not None:
            query = query.filter(WorkflowEvalRun.workflow_version_id == version_id)
        return query.order_by(WorkflowEvalRun.started_at.desc()).all()

    def touch(self, run_id: str, *, now: datetime) -> None:
        """Record that the run is being driven, before a case run starts.
        Does not commit."""
        self._get_existing(run_id).last_activity_at = now.replace(tzinfo=None)
        self.db.flush()

    def record_progress(self, run_id: str, *, now: datetime) -> None:
        """Count one more finished case run. Does not commit."""
        run = self._get_existing(run_id)
        run.case_runs_done += 1
        run.last_activity_at = now.replace(tzinfo=None)
        self.db.flush()

    def finish(self, run_id: str, *, status: str, passed: bool | None, now: datetime) -> None:
        """End a run and release the active slot. Does not commit."""
        run = self._get_existing(run_id)
        run.status = status
        run.passed = passed
        run.active_slot = None
        run.finished_at = now.replace(tzinfo=None)
        self.db.flush()

    def expire_abandoned(self, *, idle_before: datetime, now: datetime) -> int:
        """End every running run with no activity since idle_before as
        "abandoned", releasing the active slot. Does not commit.

        A run is driven by the admin's open page; one whose page was closed
        without cancelling would otherwise hold the slot forever.
        """
        abandoned = (
            self.db.query(WorkflowEvalRun)
            .filter(
                WorkflowEvalRun.status == "running",
                WorkflowEvalRun.last_activity_at < idle_before.replace(tzinfo=None),
            )
            .all()
        )
        for run in abandoned:
            self.finish(run.id, status="abandoned", passed=None, now=now)
        return len(abandoned)

    def _get_existing(self, run_id: str) -> WorkflowEvalRun:
        run = self.get(run_id)
        assert run is not None, f"eval run {run_id} does not exist"
        return run


class WorkflowEvalCaseResultRepository:
    """Insert-only scored results, one per run of a test case.

    No update or delete method by design: a recorded result is evidence.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def record(
        self,
        *,
        eval_run_id: str,
        case_name: str,
        run_index: int,
        outcome: str,
        passed: bool,
        checks: list[dict],
        thread_id: str | None,
        duration_ms: int,
        now: datetime,
    ) -> WorkflowEvalCaseResult:
        """Record one scored case run. Does not commit."""
        result = WorkflowEvalCaseResult(
            eval_run_id=eval_run_id,
            case_name=case_name,
            run_index=run_index,
            outcome=outcome,
            passed=passed,
            checks=checks,
            thread_id=thread_id,
            duration_ms=duration_ms,
            created_at=now.replace(tzinfo=None),
        )
        self.db.add(result)
        self.db.flush()
        return result

    def list_for_run(self, eval_run_id: str) -> list[WorkflowEvalCaseResult]:
        """Every result of one eval run, by case name then run index."""
        return (
            self.db.query(WorkflowEvalCaseResult)
            .filter(WorkflowEvalCaseResult.eval_run_id == eval_run_id)
            .order_by(WorkflowEvalCaseResult.case_name, WorkflowEvalCaseResult.run_index)
            .all()
        )
