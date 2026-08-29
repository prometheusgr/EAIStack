"""Tests for doc-search's core search logic.

Marked integration: ranking uses pgvector's cosine distance operator, which
only runs against real Postgres, so these live under tests/integration/ and
are not part of the CI-gating unit run.

Retrieval returns the matching chunk (chunk_text + heading_path), not
content[:300] — see issue #7 Prompt 2's chunking requirements and
backend/app/services/chunking_service.py, which produces the chunk_text/
heading_path values seeded here directly (bypassing chunk_document itself,
since these tests exercise ranking/formatting, not chunking).
"""

from uuid import uuid4

import pytest

from app.config import settings
from app.models import Embedding, KnowledgeBase, SystemSettings
from app.search import generate_query_embedding, resolve_embedding_config, search_knowledge_base


def _seed_chunk(
    db_session,
    *,
    user_id: str,
    title: str,
    chunk_text: str,
    chunk_index: int = 0,
    heading_path: str | None = None,
    doc_id: str | None = None,
) -> str:
    """Seed one KnowledgeBase (if doc_id is None) or one additional chunk on
    an existing doc_id, plus its Embedding row. Returns the doc_id, so a
    caller can seed multiple chunks for the same document.
    """
    if doc_id is None:
        kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=chunk_text)
        db_session.add(kb)
        db_session.commit()
        doc_id = kb.id

    embedding = Embedding(
        id=str(uuid4()),
        doc_id=doc_id,
        embedding=generate_query_embedding(db_session, chunk_text),
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        heading_path=heading_path,
    )
    db_session.add(embedding)
    db_session.commit()
    return doc_id


@pytest.mark.integration
def test_search_knowledge_base_returns_matching_chunk_text(db_session):
    """Returns the seeded document's title and matching chunk's text for a
    matching query, not the whole document.
    """
    _seed_chunk(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        chunk_text="Employees receive 25 days of paid vacation per year.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="vacation days", top_k=5)

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


@pytest.mark.integration
def test_search_knowledge_base_uses_hybrid_search_for_exact_token_queries(db_session):
    """search_knowledge_base itself (not just the repository directly) ranks
    an exact-token query (an error code) via hybrid search — the end-to-end
    wiring for issue #7 Prompt 3's motivating case.
    """
    _seed_chunk(
        db_session,
        user_id="user-a",
        title="ORA-01555 Troubleshooting",
        chunk_text="ORA-01555: snapshot too old. Increase UNDO_RETENTION.",
    )
    for i in range(5):
        _seed_chunk(
            db_session,
            user_id="user-a",
            title=f"Database Error Guide {i}",
            chunk_text=f"How to troubleshoot common database errors, guide {i}.",
        )

    result = search_knowledge_base(db_session, user_id="user-a", query="ORA-01555", top_k=6)

    first_result_title = result.split("\n", 1)[0]
    assert first_result_title == "Title: ORA-01555 Troubleshooting"


@pytest.mark.integration
def test_search_knowledge_base_includes_heading_path_when_present(db_session):
    """A chunk's heading path is included in the result, so the LLM sees
    which section of the document the excerpt came from.
    """
    _seed_chunk(
        db_session,
        user_id="user-a",
        title="Deployment Guide",
        chunk_text="Rotate certs every 90 days.",
        heading_path="TLS > Certificate rotation",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="certificate", top_k=5)

    assert "TLS > Certificate rotation" in result
    assert "Rotate certs every 90 days." in result


@pytest.mark.integration
def test_search_knowledge_base_omits_heading_path_line_when_none(db_session):
    """A chunk with no enclosing heading (heading_path=None) doesn't produce
    a dangling "Section: None" line in the formatted result.
    """
    _seed_chunk(
        db_session,
        user_id="user-a",
        title="Plain Doc",
        chunk_text="Just a plain paragraph.",
        heading_path=None,
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="plain", top_k=5)

    assert "None" not in result


@pytest.mark.integration
def test_search_knowledge_base_returns_empty_message_when_no_documents(db_session):
    """A clear, non-crashing message is returned when the user has no documents."""
    result = search_knowledge_base(
        db_session, user_id="user-with-no-docs", query="anything", top_k=5
    )

    assert isinstance(result, str)
    assert len(result) > 0
    assert "Vacation Policy" not in result


@pytest.mark.integration
def test_search_knowledge_base_is_scoped_to_requested_user(db_session):
    """Only documents owned by the requested user_id are returned — the
    critical isolation guarantee once search runs in a separate process from
    the backend: user_id here always comes from a verified JWT's sub claim
    (see app.auth.verify_bearer_token), never a caller-supplied string.
    """
    _seed_chunk(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        chunk_text="This document belongs only to user B.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="confidential", top_k=5)

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result


@pytest.mark.integration
def test_search_knowledge_base_truncates_chunk_text_exceeding_excerpt_cap(db_session):
    """A chunk whose own text exceeds MAX_EXCERPT_CHARS (a safety cap, not
    the primary excerpting mechanism now that chunks are already
    passage-sized) is truncated with a trailing ellipsis.
    """
    from app.search import MAX_EXCERPT_CHARS

    long_chunk = "A" * (MAX_EXCERPT_CHARS + 200)
    _seed_chunk(db_session, user_id="user-a", title="Long Doc", chunk_text=long_chunk)

    result = search_knowledge_base(db_session, user_id="user-a", query="long", top_k=5)

    assert "A" * MAX_EXCERPT_CHARS in result
    assert "..." in result
    assert "A" * (MAX_EXCERPT_CHARS + 1) not in result


@pytest.mark.integration
def test_search_knowledge_base_deduplicates_to_one_chunk_per_document(db_session):
    """Multiple matching chunks from the same document are deduplicated to
    the single highest-ranked chunk, so one document can't flood the top-k
    result set at the expense of other documents.
    """
    doc_id = _seed_chunk(
        db_session,
        user_id="user-a",
        title="Big Doc",
        chunk_text="Best matching chunk about certificates.",
        chunk_index=0,
        heading_path="Section A",
    )
    _seed_chunk(
        db_session,
        user_id="user-a",
        title="Big Doc",
        chunk_text="Second chunk about certificates too.",
        chunk_index=1,
        heading_path="Section B",
        doc_id=doc_id,
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="certificates", top_k=5)

    assert result.count("Big Doc") == 1


@pytest.mark.integration
def test_search_knowledge_base_dedup_still_returns_top_k_distinct_documents(db_session):
    """Deduplication must not shrink the result set below top_k when there
    are enough distinct matching documents — it only removes extra chunks
    from a document already represented, never reduces document coverage.
    """
    for i in range(3):
        _seed_chunk(
            db_session,
            user_id="user-a",
            title=f"Doc {i}",
            chunk_text=f"Certificate rotation content {i}.",
        )

    result = search_knowledge_base(db_session, user_id="user-a", query="certificate", top_k=3)

    assert result.count("Doc 0") + result.count("Doc 1") + result.count("Doc 2") == 3


@pytest.mark.integration
def test_search_knowledge_base_passes_bare_top_k_to_search_hybrid(db_session, monkeypatch):
    """search_knowledge_base must not pre-multiply top_k before calling
    search_hybrid — search_hybrid already widens its own per-branch
    candidate fetch internally (_CANDIDATE_MULTIPLIER, in
    app.repositories.embedding_repository), and dedup headroom comes from
    requesting that candidate pool via return_candidates=True, not from a
    second multiplier stacked on top of the first. Two independent 4x
    multipliers compounding to 16x was exactly the bug this test guards
    against.
    """
    from app.repositories import EmbeddingRepository

    _seed_chunk(db_session, user_id="user-a", title="Doc", chunk_text="certificate rotation")

    captured_kwargs = {}
    original_search_hybrid = EmbeddingRepository.search_hybrid

    def _spy_search_hybrid(self, *args, **kwargs):
        captured_kwargs.update(kwargs)
        return original_search_hybrid(self, *args, **kwargs)

    monkeypatch.setattr(EmbeddingRepository, "search_hybrid", _spy_search_hybrid)

    search_knowledge_base(db_session, user_id="user-a", query="certificate", top_k=5)

    assert captured_kwargs["top_k"] == 5
    assert captured_kwargs["return_candidates"] is True


# resolve_embedding_config: DB-override-vs-env-default resolution.
#
# Mirrors backend/tests/unit/test_system_settings_service.py's
# test_resolve_embedding_config_* tests exactly (same fixture shape, same
# scenarios) since app.search.resolve_embedding_config is a deliberate port
# of backend/app/services/system_settings_service.py's function of the same
# name, reading the same system_settings row. Marked integration like the
# rest of this file: doc-search has no SQLite fallback, so any db_session use
# needs real Postgres (see tests/conftest.py).


@pytest.mark.integration
def test_resolve_embedding_config_falls_back_to_env_settings_when_no_db_row(db_session):
    """With no SystemSettings row at all, every field comes from env settings."""
    config = resolve_embedding_config(db_session)

    assert config.provider == settings.embedding_provider
    assert config.url == settings.embedding_url
    assert config.model == settings.embedding_model
    assert config.timeout == settings.embedding_timeout


@pytest.mark.integration
def test_resolve_embedding_config_falls_back_to_env_settings_when_db_row_fields_are_null(
    db_session,
):
    """A SystemSettings row can exist (e.g. an admin previously edited LLM
    settings only) while leaving every embedding field NULL. Each must fall
    back to its env default independently — this is the case that would
    silently pass under a truthiness check on a not-None DB row just as
    easily as it does today, so it exists to pin the per-field is-not-None
    resolution, not just the "no row" case above.
    """
    db_session.add(
        SystemSettings(
            id="default",
            embedding_provider=None,
            embedding_url=None,
            embedding_model=None,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.provider == settings.embedding_provider
    assert config.url == settings.embedding_url
    assert config.model == settings.embedding_model
    assert config.timeout == settings.embedding_timeout


@pytest.mark.integration
def test_resolve_embedding_config_uses_db_override_when_present(db_session):
    """A DB row with non-null embedding fields overrides the env-var defaults
    for every overridable field.
    """
    db_session.add(
        SystemSettings(
            id="default",
            embedding_provider="llama-cpp",
            embedding_url="http://embedding-server:8000/v1",
            embedding_model="nomic-embed-text-v1.5.Q4_K_M.gguf",
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.provider == "llama-cpp"
    assert config.url == "http://embedding-server:8000/v1"
    assert config.model == "nomic-embed-text-v1.5.Q4_K_M.gguf"


@pytest.mark.integration
def test_resolve_embedding_config_falls_back_per_field_when_only_some_are_null(db_session):
    """A DB row can override just the provider and leave url/model NULL, each
    falling back to env independently (not all-or-nothing per row).
    """
    db_session.add(
        SystemSettings(
            id="default",
            embedding_provider="llama-cpp",
            embedding_url=None,
            embedding_model=None,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.provider == "llama-cpp"
    assert config.url == settings.embedding_url
    assert config.model == settings.embedding_model


@pytest.mark.integration
def test_resolve_embedding_config_treats_empty_string_db_value_as_a_real_override(db_session):
    """An empty-string DB column (e.g. the 'fake' provider's URL/model, which
    have no real endpoint) is a deliberate override, not an unset field. It
    must resolve to "" rather than silently falling back to the env default
    — this is the scenario a truthiness check (`if db_value:` instead of
    `if db_value is not None:`) would get wrong, since "" is falsy but here
    means something specific (explicitly configured empty), distinct from
    NULL ("not configured, use env default").
    """
    db_session.add(
        SystemSettings(
            id="default",
            embedding_provider="fake",
            embedding_url="",
            embedding_model="",
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.provider == "fake"
    assert config.url == ""
    assert config.model == ""


@pytest.mark.integration
def test_resolve_embedding_config_timeout_always_comes_from_env(db_session):
    """timeout is never DB-overridable — no such column exists on
    SystemSettings for embeddings (see app.models.SystemSettings), so it must
    always resolve to the env-configured value regardless of what else is
    set on the row.
    """
    db_session.add(
        SystemSettings(
            id="default",
            embedding_provider="llama-cpp",
            embedding_url="http://embedding-server:8000/v1",
            embedding_model="custom-model",
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.timeout == settings.embedding_timeout
