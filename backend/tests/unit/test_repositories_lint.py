"""Tests for the append-only repository linter (tools/lint_repositories.py).

Audit and log repositories must be append-only by structure: a
delete/update/remove/purge method on a class whose name signals it's an
audit or log store is a mutation path that shouldn't exist. This linter
is naming-convention scoped ("Audit" or "Log" in the class name), so it
covers AuditLogRepository today and any future append-only store that
follows the same naming pattern automatically.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from lint_repositories import lint_file  # noqa: E402


def _write_and_lint(tmp_path: Path, source: str) -> list:
    filepath = tmp_path / "example_repository.py"
    filepath.write_text(source, encoding="utf-8")
    return lint_file(filepath)


@pytest.mark.unit
class TestRepositoryLinter:
    def test_flags_delete_method_on_audit_repository(self, tmp_path):
        source = (
            "class AuditLogRepository:\n"
            "    def record(self) -> None:\n"
            "        pass\n"
            "\n"
            "    def delete_all(self) -> None:\n"
            "        pass\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].class_name == "AuditLogRepository"
        assert violations[0].method == "delete_all"

    def test_flags_update_method_on_log_repository(self, tmp_path):
        source = (
            "class EventLogRepository:\n" "    def update_entry(self) -> None:\n" "        pass\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert len(violations) == 1
        assert violations[0].method == "update_entry"

    def test_flags_purge_and_remove_methods(self, tmp_path):
        source = (
            "class AuditRepository:\n"
            "    def purge_old(self) -> None:\n"
            "        pass\n"
            "\n"
            "    def remove(self) -> None:\n"
            "        pass\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert {v.method for v in violations} == {"purge_old", "remove"}

    def test_allows_delete_method_on_non_audit_repository(self, tmp_path):
        source = (
            "class APIKeyRepository:\n"
            "    def revoke(self) -> None:\n"
            "        pass\n"
            "\n"
            "    def delete(self) -> None:\n"
            "        pass\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_allows_read_and_create_methods_on_audit_repository(self, tmp_path):
        source = (
            "class AuditLogRepository:\n"
            "    def record(self) -> None:\n"
            "        pass\n"
            "\n"
            "    def list_recent(self) -> list:\n"
            "        return []\n"
        )
        violations = _write_and_lint(tmp_path, source)
        assert violations == []

    def test_ignores_non_repository_classes(self, tmp_path):
        source = "class AuditLogService:\n" "    def delete_all(self) -> None:\n" "        pass\n"
        violations = _write_and_lint(tmp_path, source)
        assert violations == []
