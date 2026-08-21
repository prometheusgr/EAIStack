#!/usr/bin/env python3
"""Lint for truthiness checks on nullable int/float fields.

When None, 0, and False are all meaningful, distinct values (e.g.
conversation_retention_hours: None='keep forever', 0='purge immediately'),
`if some_field:` silently treats 0 the same as None/unset. This linter flags
`if <name>:` / `if not <name>:` where `<name>` is a parameter or class
attribute annotated `int | None` / `float | None` / `Optional[int]` /
`Optional[float]` in the same file.

Scoped to numeric Optional types only: `if some_optional_str:` legitimately
distinguishes None from "", so string/bool Optionals are not flagged.

Run via CI to gate merges that reintroduce this bug class.
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple

_NUMERIC_TYPE_NAMES = {"int", "float"}


class LintViolation(NamedTuple):
    """A single linting violation."""

    file: str
    name: str
    line: int
    severity: str  # "error" or "warning"
    message: str


def _is_nullable_numeric_annotation(annotation: ast.expr | None) -> bool:
    """True if annotation is `int | None`, `float | None`, `Optional[int]`,
    or `Optional[float]` (in either operand order for the `|` form).
    """
    if annotation is None:
        return False

    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        operands = [annotation.left, annotation.right]
        names = {op.id for op in operands if isinstance(op, ast.Name)}
        has_none = any(isinstance(op, ast.Constant) and op.value is None for op in operands)
        return has_none and bool(names & _NUMERIC_TYPE_NAMES)

    if isinstance(annotation, ast.Subscript):
        base = annotation.value
        base_name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", None)
        if base_name != "Optional":
            return False
        inner = annotation.slice
        return isinstance(inner, ast.Name) and inner.id in _NUMERIC_TYPE_NAMES

    return False


class EdgeCaseTruthinessLinter(ast.NodeVisitor):
    """AST visitor that finds truthiness checks on nullable numeric fields."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[LintViolation] = []
        self._nullable_numeric_names: set[str] = set()

    def visit_Module(self, node: ast.Module):
        self._collect_nullable_numeric_names(node)
        self.generic_visit(node)

    def _collect_nullable_numeric_names(self, node: ast.AST) -> None:
        """Find every parameter and annotated attribute in the file typed as
        a nullable int/float, so `if <name>:` can be checked against them
        regardless of which function/class the check appears in.
        """
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_args = [
                    *child.args.posonlyargs,
                    *child.args.args,
                    *child.args.kwonlyargs,
                ]
                for arg in all_args:
                    if _is_nullable_numeric_annotation(arg.annotation):
                        self._nullable_numeric_names.add(arg.arg)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                if _is_nullable_numeric_annotation(child.annotation):
                    self._nullable_numeric_names.add(child.target.id)

    def visit_If(self, node: ast.If):
        self._check_condition(node.test)
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self._check_condition(node.test)
        self.generic_visit(node)

    def _check_condition(self, test: ast.expr) -> None:
        target = (
            test.operand if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) else test
        )

        name = self._name_or_attr(target)
        if name is not None and name in self._nullable_numeric_names:
            self.violations.append(
                LintViolation(
                    file=self.filename,
                    name=name,
                    line=test.lineno,
                    severity="warning",
                    message=(
                        f"Truthiness check on nullable numeric field '{name}' treats 0 the same "
                        f"as None. Use `{name} is not None` if 0 is a meaningful, distinct value."
                    ),
                )
            )

    @staticmethod
    def _name_or_attr(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None


def lint_file(filepath: Path) -> list[LintViolation]:
    """Lint a single Python file for edge-case truthiness violations."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except SyntaxError as e:
        return [
            LintViolation(
                file=str(filepath),
                name="<parse-error>",
                line=0,
                severity="error",
                message=f"Syntax error: {e}",
            )
        ]

    linter = EdgeCaseTruthinessLinter(str(filepath))
    linter.visit(tree)
    return linter.violations


def lint_app(app_dir: Path) -> list[LintViolation]:
    """Lint all Python files in the app directory."""
    all_violations: list[LintViolation] = []

    py_files = sorted(
        f for f in app_dir.rglob("*.py") if "__pycache__" not in f.parts and "tests" not in f.parts
    )

    if not py_files:
        print(f"No Python files found in {app_dir}")
        return []

    for py_file in py_files:
        all_violations.extend(lint_file(py_file))

    return all_violations


def main():
    """Run the edge-case truthiness linter."""
    app_dir = Path(__file__).parent.parent / "app"

    if not app_dir.exists():
        print(f"App directory not found: {app_dir}")
        sys.exit(1)

    violations = lint_app(app_dir)

    if not violations:
        print("✓ No truthiness checks on nullable numeric fields found.")
        sys.exit(0)

    errors = [v for v in violations if v.severity == "error"]
    warnings = [v for v in violations if v.severity == "warning"]

    if errors:
        print("❌ EDGE-CASE TRUTHINESS VIOLATIONS (must fix):")
        for v in errors:
            print(f"  {v.file}:{v.line}")
            print(f"     {v.message}")
        print()

    if warnings:
        print("⚠️  WARNINGS (should fix — 0 may be silently treated as None):")
        for v in warnings:
            print(f"  {v.file}:{v.line}")
            print(f"     {v.message}")
        print()

    if errors:
        sys.exit(1)

    print(f"Found {len(warnings)} edge-case truthiness issue(s) (warnings only, non-blocking)")
    sys.exit(0)


if __name__ == "__main__":
    main()
