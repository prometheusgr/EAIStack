#!/usr/bin/env python3
"""Lint for e2e specs that assert on real LLM/embedding content without
being excluded from CI's fake-provider run.

CI's e2e-tests job (.github/workflows/ci.yml) runs the full stack with
LLM_PROVIDER=EMBEDDING_PROVIDER=fake (no --profile llm, no GGUF model
download) - see that job's own comment. A spec asserting on real model
*content* (e.g. "the answer contains the fact retrieved from a real
document") can never pass there, no matter how correct the application
code is, because the fake provider always returns the same canned string
regardless of input.

This was discovered the hard way: knowledge-base-search-grounding.spec.ts
shipped asserting on real grounded content, the new e2e-tests CI job ran
it against the fake provider, and it failed for an environment reason
that had nothing to do with retrieval correctness (which was separately
verified correct by hand against a real embedding server). See AGENTS.md's
"End-to-End (E2E) Tests" section for the full pattern and the required
fix shape: name the requirement, exclude the spec from CI via
--grep-invert, keep the assertion real rather than weakening it to fit
the mock.

This linter enforces the structural half of that fix going forward: any
spec file containing the `requires-profile-llm` marker comment must have
*every* one of its test() titles matching ci.yml's e2e-tests step's
--grep-invert pattern, so a new real-content spec (or a new test added to
an already-excluded file) cannot slip into CI's gating run without that
mismatch being caught immediately, not discovered by a red CI job days
later.

Checking only "at least one title matches" (an earlier version of this
linter's rule) missed exactly this: a second test() added later to an
already-marked file, whose title happened not to overlap the existing
--grep-invert pattern, silently ran in CI's fake-provider job and failed
there for an environment reason. See
test_check_e2e_ci_coverage.py::test_flags_a_marked_file_where_only_some_titles_match.

Run via CI to gate merges that reintroduce this mismatch.
"""

import re
import sys
from pathlib import Path

_MARKER = "requires-profile-llm"
_TEST_TITLE_PATTERN = re.compile(r"""test\(\s*['"](.+?)['"]""")
_GREP_INVERT_PATTERN = re.compile(r'--grep-invert\s+"([^"]+)"')


def _find_e2e_spec_files(e2e_dir: Path) -> list[Path]:
    return sorted(e2e_dir.glob("*.spec.ts"))


def _spec_has_marker(spec_path: Path) -> bool:
    return _MARKER in spec_path.read_text(encoding="utf-8")


def _extract_test_titles(spec_path: Path) -> list[str]:
    """All `test('...', ...)` / `test("...", ...)` titles in a spec file.

    Regex, not a TypeScript parser: this only needs to find literal test
    titles to check against a CI grep pattern, not understand the file's
    full syntax - the same tradeoff the backend's AST-based linters make
    in the other direction, where Python's own ast module is the natural
    fit and a regex would be the wrong tool.
    """
    return _TEST_TITLE_PATTERN.findall(spec_path.read_text(encoding="utf-8"))


def _extract_ci_grep_invert_pattern(ci_workflow_path: Path) -> str | None:
    """The --grep-invert argument CI's e2e-tests step passes to Playwright,
    or None if the step has no such flag (i.e. CI runs every spec).
    """
    match = _GREP_INVERT_PATTERN.search(ci_workflow_path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def check_e2e_ci_coverage(e2e_dir: Path, ci_workflow_path: Path) -> list[str]:
    """Return a list of violation messages; empty means everything checks out."""
    violations: list[str] = []
    ci_grep_invert_pattern = _extract_ci_grep_invert_pattern(ci_workflow_path)

    for spec_path in _find_e2e_spec_files(e2e_dir):
        if not _spec_has_marker(spec_path):
            continue

        titles = _extract_test_titles(spec_path)
        if not titles:
            violations.append(
                f"{spec_path}: has the '{_MARKER}' marker but no `test('...', ...)` "
                f"title could be found to check against CI's exclusion pattern."
            )
            continue

        if ci_grep_invert_pattern is None:
            violations.append(
                f"{spec_path}: marked '{_MARKER}' (asserts on real LLM/embedding "
                f"content), but {ci_workflow_path.name}'s e2e-tests step has no "
                f"--grep-invert flag at all, so CI runs every spec against the "
                f"fake provider - this spec will fail there for an environment "
                f"reason, not a code-correctness one. Exclude it: add "
                f'`--grep-invert "<substring of its title>"` to the e2e-tests '
                f"step's `Run e2e tests` command."
            )
            continue

        unmatched_titles = [
            title for title in titles if not re.search(ci_grep_invert_pattern, title)
        ]
        if unmatched_titles:
            violations.append(
                f"{spec_path}: marked '{_MARKER}', but {len(unmatched_titles)} of its "
                f"{len(titles)} test title(s) don't match CI's current --grep-invert "
                f"pattern ({ci_grep_invert_pattern!r}): {unmatched_titles!r} - CI is not "
                f"actually excluding {'these tests' if len(unmatched_titles) > 1 else 'this test'}, "
                f"so {'they' if len(unmatched_titles) > 1 else 'it'} will run there against "
                f"the fake provider and fail for an environment reason, not a "
                f"code-correctness one. Every test() in a file carrying the "
                f"'{_MARKER}' marker must be excluded, not just the first one added - "
                f"update {ci_workflow_path.name}'s --grep-invert pattern to also match "
                f"the title(s) listed above."
            )

    return violations


def main():
    """Run the e2e CI-coverage structural check."""
    sys.stdout.reconfigure(encoding="utf-8")
    repo_root = Path(__file__).parent.parent
    e2e_dir = repo_root / "frontend" / "tests" / "e2e"
    ci_workflow_path = repo_root / ".github" / "workflows" / "ci.yml"

    if not e2e_dir.exists():
        print(f"e2e spec directory not found: {e2e_dir}")
        sys.exit(1)
    if not ci_workflow_path.exists():
        print(f"CI workflow file not found: {ci_workflow_path}")
        sys.exit(1)

    violations = check_e2e_ci_coverage(e2e_dir, ci_workflow_path)

    if not violations:
        print(
            "✓ Every real-content e2e spec is correctly excluded from CI's fake-provider run."
        )
        sys.exit(0)

    print("❌ E2E CI COVERAGE VIOLATIONS (must fix):")
    for v in violations:
        print(f"  {v}")
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
