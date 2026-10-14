"""Tests for a workflow definition's `tests:` section (issue #84 slice B).

Test cases are part of the workflow definition, so they are validated by
app.workflows.schema at the same boundary as steps: a case that references a
step, branch or tool that doesn't exist is rejected when the version is
saved, never discovered when an eval run executes.
"""

import pytest

from app.workflows.schema import (
    EVAL_MAX_CASE_RUNS_PER_SUITE,
    EVAL_RUNS_PER_CASE_CEILING,
    WorkflowValidationError,
    parse_workflow_definition,
)


def _triage_def(tests: list[dict]) -> dict:
    return {
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
        "tests": tests,
    }


def _case(**overrides) -> dict:
    case = {
        "name": "a_case",
        "input": "How do I reset my VPN?",
        "expect": {"tool_called": "search_knowledge_base"},
    }
    case.update(overrides)
    return case


def _parse(tests: list[dict]):
    return parse_workflow_definition(_triage_def(tests), source_file="triage.yaml")


def _rejected_field(tests: list[dict]) -> str:
    with pytest.raises(WorkflowValidationError) as exc_info:
        _parse(tests)
    return exc_info.value.field


def test_a_definition_without_tests_has_an_empty_suite():
    raw = _triage_def([])
    del raw["tests"]
    assert parse_workflow_definition(raw, source_file="triage.yaml").tests == []


def test_a_case_defaults_to_one_run_that_must_pass():
    case = _parse([_case()]).tests[0]
    assert case.runs == 1
    assert case.required_passes() == 1


def test_without_min_passes_every_run_must_pass():
    assert _parse([_case(runs=3)]).tests[0].required_passes() == 3


def test_min_passes_sets_how_many_runs_must_pass():
    assert _parse([_case(runs=3, min_passes=2)]).tests[0].required_passes() == 2


def test_every_check_kind_parses():
    case = _parse(
        [
            _case(
                runs=3,
                min_passes=2,
                expect={
                    "route": {"step": "classify", "branch": "technical"},
                    "review_rounds_at_most": {"step": "draft_and_review", "rounds": 2},
                    "tool_called": "search_knowledge_base",
                    "reply_contains": ["VPN"],
                    "reply_json_schema": {"type": "object", "required": ["answer"]},
                },
            )
        ]
    ).tests[0]
    assert case.expect.route.branch == "technical"
    assert case.expect.review_rounds_at_most.rounds == 2
    assert case.expect.reply_contains == ["VPN"]


def test_an_unknown_expectation_key_is_rejected_rather_than_silently_ignored():
    # A typo must not turn into a check that never runs and always "passes".
    assert _rejected_field([_case(expect={"reply_contain": ["VPN"]})]).startswith("tests.0.expect")


def test_a_case_with_no_checks_is_rejected():
    assert _rejected_field([_case(expect={})]) == "tests.a_case.expect"


def test_duplicate_case_names_are_rejected():
    assert _rejected_field([_case(), _case()]) == "tests.a_case.name"


def test_route_check_on_a_step_that_is_not_a_route_is_rejected():
    field = _rejected_field([_case(expect={"route": {"step": "tech", "branch": "technical"}})])
    assert field == "tests.a_case.expect.route"


def test_route_check_naming_an_undeclared_branch_is_rejected():
    field = _rejected_field([_case(expect={"route": {"step": "classify", "branch": "billing"}})])
    assert field == "tests.a_case.expect.route"


def test_review_rounds_check_on_a_step_that_is_not_a_review_loop_is_rejected():
    expect = {"review_rounds_at_most": {"step": "classify", "rounds": 1}}
    assert _rejected_field([_case(expect=expect)]) == "tests.a_case.expect.review_rounds_at_most"


@pytest.mark.parametrize("rounds", [0, 4])
def test_review_rounds_outside_one_to_max_iterations_is_rejected(rounds):
    expect = {"review_rounds_at_most": {"step": "draft_and_review", "rounds": rounds}}
    assert _rejected_field([_case(expect=expect)]) == "tests.a_case.expect.review_rounds_at_most"


def test_tool_called_naming_an_unregistered_tool_is_rejected():
    field = _rejected_field([_case(expect={"tool_called": "delete_everything"})])
    assert field == "tests.a_case.expect.tool_called"


def test_min_passes_below_one_is_rejected():
    assert _rejected_field([_case(min_passes=0)]).startswith("tests.0.min_passes")


def test_min_passes_above_runs_is_rejected():
    assert _rejected_field([_case(runs=2, min_passes=3)]) == "tests.a_case.min_passes"


def test_runs_above_the_ceiling_is_rejected():
    assert _rejected_field([_case(runs=EVAL_RUNS_PER_CASE_CEILING + 1)]) == "tests.a_case.runs"


def test_runs_at_the_ceiling_is_accepted():
    assert (
        _parse([_case(runs=EVAL_RUNS_PER_CASE_CEILING)]).tests[0].runs == EVAL_RUNS_PER_CASE_CEILING
    )


def test_runs_below_one_is_rejected():
    assert _rejected_field([_case(runs=0)]).startswith("tests.0.runs")


def test_a_suite_whose_total_runs_exceed_the_ceiling_is_rejected():
    cases_needed = EVAL_MAX_CASE_RUNS_PER_SUITE // EVAL_RUNS_PER_CASE_CEILING + 1
    cases = [_case(name=f"case_{i}", runs=EVAL_RUNS_PER_CASE_CEILING) for i in range(cases_needed)]
    assert _rejected_field(cases) == "tests"


def test_an_invalid_json_schema_is_rejected():
    expect = {"reply_json_schema": {"type": "not-a-real-type"}}
    assert _rejected_field([_case(expect=expect)]) == "tests.a_case.expect.reply_json_schema"


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "pattern": "^(a+)+$"},
        {"type": "object", "patternProperties": {"^x": {"type": "string"}}},
        {"type": "object", "properties": {"answer": {"type": "string", "pattern": "a"}}},
    ],
)
def test_a_json_schema_using_regex_keywords_is_rejected(schema):
    # Same no-admin-authored-regex rule as custom guardrail patterns (#16):
    # no ReDoS surface reachable from configuration.
    expect = {"reply_json_schema": schema}
    assert _rejected_field([_case(expect=expect)]) == "tests.a_case.expect.reply_json_schema"
