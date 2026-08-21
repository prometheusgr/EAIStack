#!/usr/bin/env python3
"""Lint for delete/update methods on append-only (audit/log) repositories.

Audit and log repositories must be append-only by structure, not by
convention: a repository with a delete/update method is a repository a
future retention purge or bugfix can accidentally call. This linter
flags any `*Repository` class whose name contains "Audit" or "Log" if
it defines a method named (or starting with) update, delete, remove,
or purge.

Naming-convention scoped, matching AuditLogRepository today. A future
append-only store just needs "Audit" or "Log" in its class name to be
covered automatically; anything else is out of this linter's scope.

Run via CI to gate merges that reintroduce a mutation path onto an
append-only store.
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple

_AUDIT_NAME_MARKERS = ("Audit", "Log")
_FORBIDDEN_METHOD_PREFIXES = ("update", "delete", "remove", "purge")


class LintViolation(NamedTuple):
    """A single linting violation."""

    file: str
    class_name: str
    method: str
    line: int
    message: str


def _is_repository_class(class_name: str) -> bool:
    return class_name.endswith("Repository")


def _is_audit_shaped(class_name: str) -> bool:
    return any(marker in class_name for marker in _AUDIT_NAME_MARKERS)


def _is_forbidden_method(method_name: str) -> bool:
    return method_name.startswith(_FORBIDDEN_METHOD_PREFIXES)


class RepositoryLinter(ast.NodeVisitor):
    """AST visitor that finds mutation methods on audit-shaped repositories."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[LintViolation] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        if _is_repository_class(node.name) and _is_audit_shaped(node.name):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and _is_forbidden_method(item.name):
                    self.violations.append(
                        LintViolation(
                            file=self.filename,
                            class_name=node.name,
                            method=item.name,
                            line=item.lineno,
                            message=(
                                f"'{node.name}' looks audit/log-shaped (name contains "
                                f"'Audit' or 'Log') but defines '{item.name}()'. "
                                f"Audit and log repositories must be append-only: "
                                f"remove this method, or rename the class if it isn't "
                                f"actually an audit/log store."
                            ),
                        )
                    )
        self.generic_visit(node)


def lint_file(filepath: Path) -> list[LintViolation]:
    """Lint a single Python file for forbidden methods on audit-shaped repositories."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except SyntaxError as e:
        print(f"❌ Syntax error in {filepath}: {e}")
        sys.exit(1)

    linter = RepositoryLinter(str(filepath))
    linter.visit(tree)
    return linter.violations


def lint_repositories_dir(repositories_dir: Path) -> list[LintViolation]:
    """Lint all Python files in the repositories directory."""
    all_violations: list[LintViolation] = []

    py_files = sorted(f for f in repositories_dir.rglob("*.py") if "__pycache__" not in f.parts)

    for py_file in py_files:
        all_violations.extend(lint_file(py_file))

    return all_violations


def main():
    """Run the repository structural linter."""
    sys.stdout.reconfigure(encoding="utf-8")
    repositories_dir = Path(__file__).parent.parent / "app" / "repositories"

    if not repositories_dir.exists():
        print(f"Repositories directory not found: {repositories_dir}")
        sys.exit(1)

    violations = lint_repositories_dir(repositories_dir)

    if not violations:
        print("✓ All audit/log repositories are append-only.")
        sys.exit(0)

    print("❌ APPEND-ONLY REPOSITORY VIOLATIONS (must fix):")
    for v in violations:
        print(f"  {v.file}:{v.line} in {v.class_name}.{v.method}()")
        print(f"     {v.message}")
    print()
    sys.exit(1)


if __name__ == "__main__":
    main()
