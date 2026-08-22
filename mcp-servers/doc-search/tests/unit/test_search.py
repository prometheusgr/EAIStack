"""Tests for doc-search's core search logic.

Marked integration: ranking uses pgvector's cosine distance operator, which
only runs against real Postgres (mirrors backend's
tests/unit/test_embedding_repository.py and tests/unit/test_tools.py, which
carry the same constraint despite living under a "unit" directory name).

Behavior must match backend/app/agents/tools.py's search_knowledge_base
exactly (same excerpt formatting, same "no matches" message, same
per-user scoping) — this is a structural move, not a behavior change.
"""

from uuid import uuid4

import pytest

from app.config import settings
from app.models import Embedding, KnowledgeBase, SystemSettings
from app.search import generate_query_embedding, resolve_embedding_config, search_knowledge_base


def _seed_document(db_session, user_id: str, title: str, content: str) -> None:
    kb = KnowledgeBase(id=str(uuid4()), user_id=user_id, title=title, content=content)
    db_session.add(kb)
    db_session.commit()

    embedding = Embedding(
        id=str(uuid4()),
        doc_id=kb.id,
        embedding=generate_query_embedding(db_session, content),
    )
    db_session.add(embedding)
    db_session.commit()


@pytest.mark.integration
def test_search_knowledge_base_returns_matching_document_content(db_session):
    """Returns the seeded document's title and content excerpt for a matching query."""
    _seed_document(
        db_session,
        user_id="user-a",
        title="Vacation Policy",
        content="Employees receive 25 days of paid vacation per year.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="vacation days", top_k=5)

    assert "Vacation Policy" in result
    assert "25 days of paid vacation" in result


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
    _seed_document(
        db_session,
        user_id="user-b",
        title="User B Confidential Doc",
        content="This document belongs only to user B.",
    )

    result = search_knowledge_base(db_session, user_id="user-a", query="confidential", top_k=5)

    assert "User B Confidential Doc" not in result
    assert "belongs only to user B" not in result


@pytest.mark.integration
def test_search_knowledge_base_truncates_long_content_with_ellipsis(db_session):
    """Content longer than the excerpt limit is truncated with a trailing ellipsis."""
    long_content = "A" * 500
    _seed_document(db_session, user_id="user-a", title="Long Doc", content=long_content)

    result = search_knowledge_base(db_session, user_id="user-a", query="long", top_k=5)

    assert "A" * 300 in result
    assert "..." in result
    assert "A" * 301 not in result


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
