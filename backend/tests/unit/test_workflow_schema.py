"""Tests for YAML workflow definition validation (app.workflows.schema).

Each test constructs a definition as a plain dict (the shape yaml.safe_load
would produce) rather than writing a .yaml fixture file to disk — schema
validation is pure and doesn't care about the file format, only the
parsed structure. app.workflows.loader's own tests cover the
file-reading/parsing step.
"""

import pytest

from app.workflows.schema import (
    REVIEW_LOOP_MAX_ITERATIONS_CEILING,
    WorkflowValidationError,
    parse_workflow_definition,
)


def _valid_single_agent_def() -> dict:
    return {
        "name": "chat",
        "version": 1,
        "entry": "respond",
        "steps": {
            "respond": {
                "type": "agent",
                "prompt": "You are a helpful assistant.",
                "tools": ["search_knowledge_base"],
            }
        },
    }


def test_valid_single_agent_definition_parses():
    definition = parse_workflow_definition(_valid_single_agent_def(), source_file="chat.yaml")
    assert definition.name == "chat"
    assert definition.entry == "respond"
    assert "respond" in definition.steps


def test_valid_sequence_definition_parses():
    raw = {
        "name": "draft_and_polish",
        "version": 1,
        "entry": "draft",
        "steps": {
            "draft": {"type": "agent", "prompt": "Draft a reply.", "next": "polish"},
            "polish": {"type": "agent", "prompt": "Polish the reply."},
        },
    }
    definition = parse_workflow_definition(raw, source_file="draft_and_polish.yaml")
    assert definition.steps["draft"].next == "polish"


def test_valid_review_loop_definition_parses():
    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "worker",
        "steps": {
            "worker": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Draft an answer.",
                "reviewer_prompt": "Review the answer; reply 'approve' or 'reject: <why>'.",
                "approve_keyword": "approve",
                "max_iterations": 3,
            }
        },
    }
    definition = parse_workflow_definition(raw, source_file="reviewed_answer.yaml")
    assert definition.steps["worker"].max_iterations == 3


def test_unknown_tool_name_is_rejected():
    raw = _valid_single_agent_def()
    raw["steps"]["respond"]["tools"] = ["not_a_real_tool"]

    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="chat.yaml")

    assert exc_info.value.file == "chat.yaml"
    assert "not_a_real_tool" in exc_info.value.message


def test_entry_referencing_undefined_step_is_rejected():
    raw = _valid_single_agent_def()
    raw["entry"] = "does_not_exist"

    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="chat.yaml")

    assert "does_not_exist" in exc_info.value.message


def test_sequence_next_referencing_undefined_step_is_rejected():
    raw = {
        "name": "broken_sequence",
        "version": 1,
        "entry": "draft",
        "steps": {
            "draft": {"type": "agent", "prompt": "Draft a reply.", "next": "nonexistent_step"},
        },
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="broken_sequence.yaml")

    assert "nonexistent_step" in exc_info.value.message


def test_unreachable_step_is_rejected():
    raw = {
        "name": "has_orphan",
        "version": 1,
        "entry": "draft",
        "steps": {
            "draft": {"type": "agent", "prompt": "Draft a reply."},
            "orphan": {"type": "agent", "prompt": "Never reached."},
        },
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="has_orphan.yaml")

    assert "orphan" in exc_info.value.message


def test_review_loop_without_max_iterations_is_rejected():
    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "worker",
        "steps": {
            "worker": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Draft an answer.",
                "reviewer_prompt": "Review it.",
                "approve_keyword": "approve",
            }
        },
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="reviewed_answer.yaml")

    assert "max_iterations" in exc_info.value.message


def test_review_loop_max_iterations_above_ceiling_is_rejected():
    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "worker",
        "steps": {
            "worker": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Draft an answer.",
                "reviewer_prompt": "Review it.",
                "approve_keyword": "approve",
                "max_iterations": REVIEW_LOOP_MAX_ITERATIONS_CEILING + 1,
            }
        },
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="reviewed_answer.yaml")

    assert "max_iterations" in exc_info.value.message
    assert str(REVIEW_LOOP_MAX_ITERATIONS_CEILING) in exc_info.value.message


def test_review_loop_at_ceiling_is_accepted():
    raw = {
        "name": "reviewed_answer",
        "version": 1,
        "entry": "worker",
        "steps": {
            "worker": {
                "type": "review_loop",
                "worker_step": "worker_agent",
                "reviewer_step": "reviewer_agent",
                "worker_prompt": "Draft an answer.",
                "reviewer_prompt": "Review it.",
                "approve_keyword": "approve",
                "max_iterations": REVIEW_LOOP_MAX_ITERATIONS_CEILING,
            }
        },
    }
    definition = parse_workflow_definition(raw, source_file="reviewed_answer.yaml")
    assert definition.steps["worker"].max_iterations == REVIEW_LOOP_MAX_ITERATIONS_CEILING


def test_route_referencing_undefined_branch_step_is_rejected():
    raw = {
        "name": "triage",
        "version": 1,
        "entry": "classify",
        "steps": {
            "classify": {
                "type": "route",
                "prompt": "Classify the request as billing or support.",
                "branches": {"billing": "billing_agent", "support": "does_not_exist"},
            },
            "billing_agent": {"type": "agent", "prompt": "Handle billing."},
        },
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        parse_workflow_definition(raw, source_file="triage.yaml")

    assert "does_not_exist" in exc_info.value.message
