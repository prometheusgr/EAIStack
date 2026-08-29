"""Pins doc-search's repository surface to read-only methods.

Marked unit, and deliberately free of any database fixture: this asserts a
fact about the class definition, not about query behavior, so it must run in
the CI-gating unit suite rather than only when Docker/testcontainers are
available. The behavioral tests for search_similar live in
tests/integration/test_embedding_repository.py, where real Postgres (and
pgvector's cosine distance operator) is actually required.

Mirrors backend/tests/unit/test_audit_log_repository.py's
test_repository_exposes_no_delete_or_update_method.
"""

import pytest

from app.repositories import EmbeddingRepository


@pytest.mark.unit
def test_embedding_repository_exposes_no_write_method():
    """The repository must be structurally incapable of writing to the schema.

    This is the code-level enforcement of doc-search's read-only contract
    (see app/models.py's module docstring): Alembic in backend/ owns the
    schema, and doc-search only ever reads it. The backend's own
    EmbeddingRepository has update_metadata/soft_delete; those are
    deliberately not ported here, so no code path in this service can
    acquire one by accident. A write method added in a future edit fails
    this test before it can reach a caller.

    search_hybrid (issue #7 Prompt 3) is a second read method, added
    deliberately alongside this update to the expected set - it fuses
    search_similar's vector ranking with a Postgres full-text search branch
    (_search_lexical, private and so already excluded by the
    not-underscore-prefixed filter below), still read-only end to end.

    Asserted against the class, not an instance, so no database session is
    needed to check it.
    """
    public_methods = {name for name in dir(EmbeddingRepository) if not name.startswith("_")}

    assert public_methods == {"search_similar", "search_hybrid"}, (
        "doc-search's EmbeddingRepository surface changed. It must stay read-only: "
        "adding a write method here would silently widen this service's contract "
        "beyond the read-only guarantee documented in app/models.py and README.md."
    )
