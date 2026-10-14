"""Tests for app.workflows.eval_scoring (issue #84 slice B).

Scoring is pure: it judges an already-observed run against a test case's
checks, with no LLM, database or graph involved.
"""

import pytest

from app.workflows.eval_scoring import (
    CaseRunObservation,
    case_passed,
    run_passed,
    score_case_run,
)
from app.workflows.primitives import review_rounds_key
from app.workflows.schema import parse_workflow_definition

_REPLY = '{"answer": "Open Settings, then VPN, then Reset."}'


def _definition(expect: dict, **case_fields):
    raw = {
        "name": "triage",
        "version": 1,
        "entry": "classify",
        "steps": {
            "classify": {
                "type": "route",
                "prompt": "Classify.",
                "branches": {"technical": "tech", "general": "draft_and_review"},
            },
            "tech": {"type": "agent", "prompt": "Tech.", "tools": ["search_knowledge_base"]},
            "draft_and_review": {
                "type": "review_loop",
                "worker_step": "worker",
                "reviewer_step": "reviewer",
                "worker_prompt": "Work.",
                "reviewer_prompt": "Review.",
                "max_iterations": 3,
            },
        },
        "tests": [{"name": "a_case", "input": "Reset my VPN", "expect": expect, **case_fields}],
    }
    return parse_workflow_definition(raw, source_file="triage.yaml")


def _score(expect: dict, observation: CaseRunObservation):
    definition = _definition(expect)
    return score_case_run(definition.tests[0], definition, observation)


def _completed(**fields) -> CaseRunObservation:
    return CaseRunObservation(outcome="completed", **fields)


def _only(results):
    assert len(results) == 1
    return results[0]


def test_route_check_passes_when_the_classifier_output_selects_the_expected_branch():
    result = _only(
        _score(
            {"route": {"step": "classify", "branch": "technical"}},
            _completed(step_outputs={"classify": "technical"}),
        )
    )
    assert result.passed is True
    assert result.kind == "structural"


def test_route_check_fails_naming_the_branch_actually_taken():
    result = _only(
        _score(
            {"route": {"step": "classify", "branch": "technical"}},
            _completed(step_outputs={"classify": "general"}),
        )
    )
    assert result.passed is False
    assert "'general'" in result.detail


def test_route_check_judges_unmatched_output_the_way_the_router_does():
    # The router falls back to the first declared branch, so an unmatched
    # classifier output did route to 'technical'.
    result = _only(
        _score(
            {"route": {"step": "classify", "branch": "technical"}},
            _completed(step_outputs={"classify": "no idea"}),
        )
    )
    assert result.passed is True


def test_route_check_fails_when_the_route_step_never_ran():
    result = _only(
        _score({"route": {"step": "classify", "branch": "technical"}}, _completed(step_outputs={}))
    )
    assert result.passed is False
    assert "did not run" in result.detail


@pytest.mark.parametrize("rounds_taken, passed", [(1, True), (2, True), (3, False)])
def test_review_rounds_check_compares_rounds_taken_with_the_limit(rounds_taken, passed):
    result = _only(
        _score(
            {"review_rounds_at_most": {"step": "draft_and_review", "rounds": 2}},
            _completed(step_outputs={review_rounds_key("reviewer"): str(rounds_taken)}),
        )
    )
    assert result.passed is passed


def test_review_rounds_check_fails_when_the_loop_never_ran():
    result = _only(
        _score(
            {"review_rounds_at_most": {"step": "draft_and_review", "rounds": 2}},
            _completed(step_outputs={}),
        )
    )
    assert result.passed is False
    assert "did not run" in result.detail


@pytest.mark.parametrize(
    "tools_called, passed", [(frozenset({"search_knowledge_base"}), True), (frozenset(), False)]
)
def test_tool_called_check(tools_called, passed):
    result = _only(
        _score({"tool_called": "search_knowledge_base"}, _completed(tools_called=tools_called))
    )
    assert result.passed is passed


def test_reply_contains_is_one_case_insensitive_check_per_substring():
    results = _score({"reply_contains": ["vpn", "billing"]}, _completed(reply=_REPLY))
    assert [(r.check, r.passed) for r in results] == [
        ("reply_contains", True),
        ("reply_contains", False),
    ]
    assert results[0].kind == "content"


def test_reply_json_schema_passes_for_a_conforming_reply():
    schema = {"type": "object", "required": ["answer"]}
    assert _only(_score({"reply_json_schema": schema}, _completed(reply=_REPLY))).passed is True


def test_reply_json_schema_fails_for_a_reply_that_is_not_json():
    result = _only(
        _score({"reply_json_schema": {"type": "object"}}, _completed(reply="Sure! Here you go."))
    )
    assert result.passed is False
    assert result.detail == "reply is not valid JSON"


def test_reply_json_schema_failure_names_the_failing_schema_location():
    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    result = _only(_score({"reply_json_schema": schema}, _completed(reply=_REPLY)))
    assert result.passed is False
    assert "properties/answer/type" in result.detail


@pytest.mark.parametrize(
    "expect",
    [
        {"reply_contains": ["refund policy"]},
        {"reply_json_schema": {"type": "object", "properties": {"answer": {"type": "integer"}}}},
        {"reply_json_schema": {"type": "object", "additionalProperties": False}},
    ],
)
def test_failure_details_never_quote_the_reply(expect):
    # Eval results are kept indefinitely as publish evidence, so they must
    # hold no conversation content (see docs/SECURITY.md's retention table).
    secret_reply = '{"answer": "SECRET-CONTENT-123"}'
    for result in _score(expect, _completed(reply=secret_reply)):
        assert "SECRET-CONTENT-123" not in result.detail


@pytest.mark.parametrize(
    "outcome, detail_fragment",
    [
        ("timed_out", "timed out"),
        ("rejected_by_input_guardrail", "input guardrail"),
        ("error", "error"),
    ],
)
def test_a_run_that_did_not_complete_fails_every_check(outcome, detail_fragment):
    results = _score(
        {"tool_called": "search_knowledge_base", "reply_contains": ["vpn"]},
        CaseRunObservation(outcome=outcome),
    )
    assert len(results) == 2
    assert all(not r.passed and detail_fragment in r.detail for r in results)


def test_run_passed_requires_every_check_to_pass():
    results = _score(
        {"tool_called": "search_knowledge_base", "reply_contains": ["vpn"]},
        _completed(reply=_REPLY, tools_called=frozenset()),
    )
    assert run_passed(results) is False


def test_run_passed_is_false_when_nothing_was_checked():
    assert run_passed([]) is False


@pytest.mark.parametrize(
    "case_fields, run_outcomes, passed",
    [
        ({}, [True], True),
        ({}, [False], False),
        ({"runs": 3}, [True, True, False], False),
        ({"runs": 3, "min_passes": 2}, [True, True, False], True),
        ({"runs": 3, "min_passes": 2}, [True, False, False], False),
    ],
)
def test_case_passed_compares_passing_runs_with_the_required_number(
    case_fields, run_outcomes, passed
):
    case = _definition({"tool_called": "search_knowledge_base"}, **case_fields).tests[0]
    assert case_passed(case, run_outcomes) is passed
