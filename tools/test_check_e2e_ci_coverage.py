"""Unit tests for check_e2e_ci_coverage.py - TDD discipline.

Regression coverage for a real CI failure: output-guardrail-redaction-
indicator.spec.ts carries the requires-profile-llm marker and has two
test() calls, but ci.yml's --grep-invert pattern only matched the first
title. The second test ("reopening the thread...") silently ran against
CI's fake-provider e2e-tests job and failed there for an environment
reason (the fake LLM never produces the real-model content it asserts
on), not a code-correctness one -- exactly the failure mode this linter
exists to catch before merge, but couldn't, because it only checked that
*some* title in a marked file matched, not *every* title.
"""

import textwrap
from pathlib import Path

import pytest
from check_e2e_ci_coverage import check_e2e_ci_coverage

pytestmark = pytest.mark.unit


def _write_spec(tmp_path: Path, name: str, content: str) -> Path:
    e2e_dir = tmp_path / "frontend" / "tests" / "e2e"
    e2e_dir.mkdir(parents=True, exist_ok=True)
    spec_path = e2e_dir / name
    spec_path.write_text(textwrap.dedent(content), encoding="utf-8")
    return spec_path


def _write_ci_workflow(tmp_path: Path, grep_invert_pattern: str | None) -> Path:
    ci_dir = tmp_path / ".github" / "workflows"
    ci_dir.mkdir(parents=True, exist_ok=True)
    ci_path = ci_dir / "ci.yml"
    invert_line = (
        f'        run: npx playwright test tests/e2e/ --grep-invert "{grep_invert_pattern}"'
        if grep_invert_pattern is not None
        else "        run: npx playwright test tests/e2e/"
    )
    ci_path.write_text(
        f"e2e-tests:\n  steps:\n    - name: Run e2e tests\n{invert_line}\n"
    )
    return ci_path


def test_passes_when_every_title_in_a_marked_file_matches(tmp_path):
    spec_path = _write_spec(
        tmp_path,
        "example.spec.ts",
        """
        // requires-profile-llm
        test('a real model does thing one', async ({ page }) => {})
        test('a real model does thing two', async ({ page }) => {})
        """,
    )
    ci_path = _write_ci_workflow(tmp_path, "does thing one|does thing two")

    violations = check_e2e_ci_coverage(spec_path.parent, ci_path)

    assert violations == []


def test_flags_a_marked_file_where_only_some_titles_match(tmp_path):
    """Regression test for the real bug: a second test() added later to an
    already-marked file must be caught if its title isn't also excluded --
    not silently left to fail in CI's fake-provider run.
    """
    spec_path = _write_spec(
        tmp_path,
        "output-guardrail-redaction-indicator.spec.ts",
        """
        // requires-profile-llm
        test('a real system-prompt disclosure is redacted and shows the content-safety indicator', async ({ page }) => {})
        test('reopening the thread still shows redacted text, not the original disclosure', async ({ page }) => {})
        """,
    )
    ci_path = _write_ci_workflow(
        tmp_path, "grounded in a document|content-safety indicator"
    )

    violations = check_e2e_ci_coverage(spec_path.parent, ci_path)

    assert len(violations) == 1
    assert "reopening the thread" in violations[0]


def test_flags_a_marked_file_with_no_grep_invert_flag_at_all(tmp_path):
    spec_path = _write_spec(
        tmp_path,
        "example.spec.ts",
        """
        // requires-profile-llm
        test('a real model does something', async ({ page }) => {})
        """,
    )
    ci_path = _write_ci_workflow(tmp_path, None)

    violations = check_e2e_ci_coverage(spec_path.parent, ci_path)

    assert len(violations) == 1
    assert "no --grep-invert flag at all" in violations[0]


def test_ignores_an_unmarked_file_regardless_of_its_titles(tmp_path):
    spec_path = _write_spec(
        tmp_path,
        "ordinary.spec.ts",
        """
        test('a fake-provider-safe test', async ({ page }) => {})
        """,
    )
    ci_path = _write_ci_workflow(tmp_path, "something unrelated")

    violations = check_e2e_ci_coverage(spec_path.parent, ci_path)

    assert violations == []
