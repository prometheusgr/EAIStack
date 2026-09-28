"""Tests for app.workflows.loader: reading *.yaml files from a directory,
parsing and validating each into a WorkflowDef.
"""

import pytest

from app.workflows.loader import load_workflow_definitions
from app.workflows.schema import WorkflowValidationError


def _write(tmp_path, filename: str, content: str) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")


def test_loads_one_valid_workflow_file(tmp_path):
    _write(
        tmp_path,
        "chat.yaml",
        """
name: chat
version: 1
entry: respond
steps:
  respond:
    type: agent
    prompt: You are a helpful assistant.
    tools:
      - search_knowledge_base
""",
    )

    definitions = load_workflow_definitions(str(tmp_path))

    assert "chat" in definitions
    assert definitions["chat"].entry == "respond"


def test_loads_multiple_workflow_files(tmp_path):
    _write(
        tmp_path,
        "chat.yaml",
        """
name: chat
version: 1
entry: respond
steps:
  respond:
    type: agent
    prompt: You are a helpful assistant.
""",
    )
    _write(
        tmp_path,
        "second.yaml",
        """
name: second
version: 1
entry: respond
steps:
  respond:
    type: agent
    prompt: A second workflow.
""",
    )

    definitions = load_workflow_definitions(str(tmp_path))

    assert set(definitions.keys()) == {"chat", "second"}


def test_invalid_yaml_file_raises_with_file_name(tmp_path):
    _write(
        tmp_path,
        "broken.yaml",
        """
name: broken
version: 1
entry: does_not_exist
steps:
  respond:
    type: agent
    prompt: Hello.
""",
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        load_workflow_definitions(str(tmp_path))

    assert exc_info.value.file == "broken.yaml"


def test_empty_directory_loads_no_workflows(tmp_path):
    assert load_workflow_definitions(str(tmp_path)) == {}


def test_non_yaml_files_are_ignored(tmp_path):
    _write(tmp_path, "readme.md", "not a workflow")
    _write(
        tmp_path,
        "chat.yaml",
        """
name: chat
version: 1
entry: respond
steps:
  respond:
    type: agent
    prompt: You are a helpful assistant.
""",
    )

    definitions = load_workflow_definitions(str(tmp_path))

    assert set(definitions.keys()) == {"chat"}
