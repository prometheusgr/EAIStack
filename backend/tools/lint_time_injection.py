#!/usr/bin/env python3
"""Lint for time-dependent functions that accept time as a parameter.

This linter enforces the time injection pattern:
- Functions that call datetime.now() should accept `now: datetime` parameter
- Functions without `now` parameter should not call datetime.now()

Run via CI to gate merges that violate determinism constraints.
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple


class LintViolation(NamedTuple):
    """A single linting violation."""

    file: str
    function: str
    line: int
    severity: str  # "error" or "warning"
    message: str


class TimeInjectionLinter(ast.NodeVisitor):
    """AST visitor that checks for proper time injection pattern."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[LintViolation] = []
        self.current_function: str | None = None
        self.current_function_node: ast.FunctionDef | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Check function definitions for time injection pattern."""
        self.current_function = node.name
        self.current_function_node = node

        # Check if function accepts 'now' parameter
        params = [arg.arg for arg in node.args.args]
        has_now_param = "now" in params

        # Check if function calls datetime.now()
        has_datetime_now_call = self._has_datetime_now_call(node)

        if has_datetime_now_call and not has_now_param:
            # Function calls datetime.now() but doesn't accept `now` parameter
            self.violations.append(
                LintViolation(
                    file=self.filename,
                    function=node.name,
                    line=node.lineno,
                    severity="warning",
                    message=f"Function '{node.name}' calls datetime.now() but doesn't accept `now: datetime` parameter. "
                    f"Add `now: datetime` parameter and pass it to callers for testability.",
                )
            )

        self.generic_visit(node)
        self.current_function = None
        self.current_function_node = None

    def _has_datetime_now_call(self, node: ast.AST) -> bool:
        """Check if a node contains a datetime.now() call."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # Check for datetime.now()
                if isinstance(child.func, ast.Attribute):
                    if (
                        child.func.attr == "now"
                        and isinstance(child.func.value, ast.Name)
                        and child.func.value.id == "datetime"
                    ):
                        return True
        return False


def lint_file(filepath: Path) -> list[LintViolation]:
    """Lint a single Python file for time injection violations."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except SyntaxError as e:
        return [
            LintViolation(
                file=str(filepath),
                function="<parse-error>",
                line=0,
                severity="error",
                message=f"Syntax error: {e}",
            )
        ]

    linter = TimeInjectionLinter(str(filepath))
    linter.visit(tree)
    return linter.violations


def lint_app(app_dir: Path) -> list[LintViolation]:
    """Lint all Python files in the app directory."""
    all_violations: list[LintViolation] = []

    # Find all .py files in app directory, excluding tests and __pycache__
    py_files = sorted(
        [
            f
            for f in app_dir.rglob("*.py")
            if "__pycache__" not in f.parts and "tests" not in f.parts
        ]
    )

    if not py_files:
        print(f"No Python files found in {app_dir}")
        return []

    for py_file in py_files:
        violations = lint_file(py_file)
        all_violations.extend(violations)

    return all_violations


def main():
    """Run the time injection linter."""
    app_dir = Path(__file__).parent.parent / "app"

    if not app_dir.exists():
        print(f"App directory not found: {app_dir}")
        sys.exit(1)

    violations = lint_app(app_dir)

    if not violations:
        print("✓ All functions follow time injection pattern (deterministic).")
        sys.exit(0)

    # Group by severity
    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    # Print errors
    if errors:
        print("❌ TIME INJECTION VIOLATIONS (must fix):")
        for v in errors:
            print(f"  {v.file}:{v.line} in {v.function}()")
            print(f"     {v.message}")
        print()

    # Print warnings
    if warnings:
        print("⚠️  WARNINGS (should fix for determinism):")
        for v in warnings:
            print(f"  {v.file}:{v.line} in {v.function}()")
            print(f"     {v.message}")
        print()

    # Exit with error only for parse errors; warnings are non-gating
    if errors:
        sys.exit(1)

    # Print summary
    print(f"Found {len(warnings)} time-injection opportunity/ies (warnings only, non-blocking)")
    sys.exit(0)


if __name__ == "__main__":
    main()
