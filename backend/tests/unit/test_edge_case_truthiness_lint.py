"""Tests for the edge-case truthiness linter (tools/lint_edge_case_truthiness.py).

Optional[int|float] parameters and attributes can hold 0 as a meaningful,
present value (e.g. conversation_retention_hours=0 means "purge immediately").
A bare truthiness check (`if x:`) cannot distinguish 0 from None/unset.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from lint_edge_case_truthiness import lint_file  # noqa: E402


def _write_and_lint(tmp_path: Path, source: str) -> list:
    filepath = tmp_path / "example.py"
    filepath.write_text(source, encoding="utf-8")
    return lint_file(filepath)


@pytest.mark.unit
class TestEdgeCaseTruthinessLinter:
    def test_flags_if_check_on_nullable_int_param(self, tmp_path):
        source = (
            "def resolve(retention_hours: int | None) -> int:\n"
            "    if retention_hours:\n"
            "        return retention_hours\n"
            "    return 24\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].name == "retention_hours"

    def test_flags_not_check_on_nullable_float_param(self, tmp_path):
        source = (
            "def scale(factor: float | None) -> float:\n"
            "    if not factor:\n"
            "        return 1.0\n"
            "    return factor\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].name == "factor"

    def test_flags_while_check_on_nullable_int_param(self, tmp_path):
        source = (
            "def countdown(remaining: int | None) -> None:\n"
            "    while remaining:\n"
            "        remaining -= 1\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].name == "remaining"

    def test_flags_typing_optional_spelling(self, tmp_path):
        source = (
            "from typing import Optional\n"
            "\n"
            "def resolve(count: Optional[int]) -> int:\n"
            "    if count:\n"
            "        return count\n"
            "    return 0\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].name == "count"

    def test_flags_class_attribute_used_in_other_function(self, tmp_path):
        source = (
            "class Settings:\n"
            "    retention_hours: int | None = None\n"
            "\n"
            "def check(settings):\n"
            "    if settings.retention_hours:\n"
            "        pass\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].name == "retention_hours"

    def test_does_not_flag_is_none_check(self, tmp_path):
        source = (
            "def resolve(retention_hours: int | None) -> int:\n"
            "    if retention_hours is None:\n"
            "        return 24\n"
            "    return retention_hours\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_does_not_flag_non_optional_param(self, tmp_path):
        source = (
            "def resolve(retention_hours: int) -> int:\n"
            "    if retention_hours:\n"
            "        return retention_hours\n"
            "    return 24\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_does_not_flag_nullable_str_param(self, tmp_path):
        source = (
            "def label(name: str | None) -> str:\n"
            "    if name:\n"
            "        return name\n"
            "    return 'default'\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_does_not_flag_nullable_bool_param(self, tmp_path):
        source = (
            "def check(enabled: bool | None) -> bool:\n"
            "    if enabled:\n"
            "        return True\n"
            "    return False\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_does_not_flag_nullable_list_param(self, tmp_path):
        source = (
            "def resolve(items: list | None) -> list:\n"
            "    if items:\n"
            "        return items\n"
            "    return []\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []
