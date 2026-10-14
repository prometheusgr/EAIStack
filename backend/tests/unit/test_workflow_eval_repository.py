"""Unit tests for the eval-run stores (issue #84 slice B) - TDD."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories import (
    EvalRunInProgress,
    WorkflowEvalCaseResultRepository,
    WorkflowEvalRunRepository,
    WorkflowVersionRepository,
)

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
CHAT_YAML = (
    "name: chat\nversion: 1\nentry: respond\nsteps:\n  respond:\n    type: agent\n    prompt: hi\n"
)


@pytest.fixture
def version_id(db_session) -> str:
    version = WorkflowVersionRepository(db_session).add(
        workflow_name="chat",
        yaml_text=CHAT_YAML,
        source="admin",
        author_user_id="admin-1",
        change_note="first",
        parent_version_id=None,
        now=NOW,
    )
    db_session.commit()
    return version.id


def _start(db_session, version_id, *, now=NOW, total=3):
    run = WorkflowEvalRunRepository(db_session).start(
        workflow_name="chat",
        workflow_version_id=version_id,
        case_runs_total=total,
        started_by_user_id="admin-1",
        now=now,
    )
    db_session.commit()
    return run


def _record(results, run_id, case_name="a", run_index=0):
    return results.record(
        eval_run_id=run_id,
        case_name=case_name,
        run_index=run_index,
        outcome="completed",
        passed=True,
        checks=[{"check": "tool_called", "kind": "structural", "passed": True, "detail": "ok"}],
        thread_id=None,
        duration_ms=10,
        now=NOW,
    )


@pytest.mark.unit
def test_a_started_run_is_running_with_no_progress_and_no_verdict(db_session, version_id):
    run = _start(db_session, version_id)
    assert (run.status, run.case_runs_done, run.passed) == ("running", 0, None)


@pytest.mark.unit
def test_a_second_run_cannot_start_while_one_is_running(db_session, version_id):
    _start(db_session, version_id)
    with pytest.raises(EvalRunInProgress):
        _start(db_session, version_id)


@pytest.mark.unit
def test_a_new_run_can_start_once_the_previous_one_finished(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    first = _start(db_session, version_id)
    repo.finish(first.id, status="completed", passed=True, now=NOW)
    db_session.commit()

    assert _start(db_session, version_id).status == "running"


@pytest.mark.unit
def test_finish_records_status_verdict_and_end_time(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    run = _start(db_session, version_id)

    repo.finish(run.id, status="completed", passed=False, now=NOW + timedelta(minutes=5))
    db_session.commit()

    finished = repo.get(run.id)
    assert (finished.status, finished.passed) == ("completed", False)
    assert finished.finished_at == (NOW + timedelta(minutes=5)).replace(tzinfo=None)


@pytest.mark.unit
def test_record_progress_counts_completed_case_runs_as_activity(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    run = _start(db_session, version_id)

    repo.record_progress(run.id, now=NOW + timedelta(minutes=1))
    repo.record_progress(run.id, now=NOW + timedelta(minutes=2))
    db_session.commit()

    progressed = repo.get(run.id)
    assert progressed.case_runs_done == 2
    assert progressed.last_activity_at == (NOW + timedelta(minutes=2)).replace(tzinfo=None)


@pytest.mark.unit
def test_touch_records_activity_without_progress(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    run = _start(db_session, version_id)

    repo.touch(run.id, now=NOW + timedelta(minutes=3))

    touched = repo.get(run.id)
    assert touched.case_runs_done == 0
    assert touched.last_activity_at == (NOW + timedelta(minutes=3)).replace(tzinfo=None)


@pytest.mark.unit
def test_expire_abandoned_ends_only_runs_idle_since_before_the_cutoff(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    run = _start(db_session, version_id, now=NOW)

    assert repo.expire_abandoned(idle_before=NOW, now=NOW) == 0
    assert repo.get(run.id).status == "running"

    assert repo.expire_abandoned(idle_before=NOW + timedelta(seconds=1), now=NOW) == 1
    db_session.commit()
    assert repo.get(run.id).status == "abandoned"
    # ...and the slot is free again.
    assert _start(db_session, version_id).status == "running"


@pytest.mark.unit
def test_list_for_workflow_is_newest_first_and_filters_by_version(db_session, version_id):
    repo = WorkflowEvalRunRepository(db_session)
    older = _start(db_session, version_id, now=NOW)
    repo.finish(older.id, status="completed", passed=True, now=NOW)
    newer = _start(db_session, version_id, now=NOW + timedelta(hours=1))

    assert [r.id for r in repo.list_for_workflow("chat")] == [newer.id, older.id]
    assert repo.list_for_workflow("chat", version_id="other") == []
    assert repo.list_for_workflow("triage") == []


@pytest.mark.unit
def test_case_results_are_listed_in_case_then_run_order(db_session, version_id):
    run = _start(db_session, version_id)
    results = WorkflowEvalCaseResultRepository(db_session)
    for case_name, run_index in [("b", 0), ("a", 1), ("a", 0)]:
        _record(results, run.id, case_name, run_index)
    db_session.commit()

    listed = results.list_for_run(run.id)

    assert [(r.case_name, r.run_index) for r in listed] == [("a", 0), ("a", 1), ("b", 0)]
    assert listed[0].checks[0]["check"] == "tool_called"


@pytest.mark.unit
def test_the_same_case_run_cannot_be_recorded_twice(db_session, version_id):
    run = _start(db_session, version_id)
    results = WorkflowEvalCaseResultRepository(db_session)
    _record(results, run.id)

    with pytest.raises(IntegrityError):
        _record(results, run.id)


@pytest.mark.unit
def test_case_result_repository_exposes_no_way_to_mutate_or_delete_a_result():
    public_methods = {
        name for name in dir(WorkflowEvalCaseResultRepository) if not name.startswith("_")
    }
    assert public_methods == {"record", "list_for_run"}
