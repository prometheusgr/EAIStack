"""TDD tests for SystemSettingsRepository - the singleton runtime settings row."""

import pytest

from app.repositories.system_settings_repository import SystemSettingsRepository


@pytest.mark.unit
def test_get_returns_none_before_any_row_exists(db_session):
    """No settings row has been created yet, so get() should return None
    (the service layer falls back to env-var settings in that case).
    """
    repo = SystemSettingsRepository(db_session)

    result = repo.get()

    assert result is None


@pytest.mark.unit
def test_upsert_creates_singleton_row_when_none_exists(db_session):
    """The first upsert() call creates the id='default' row with the given fields."""
    repo = SystemSettingsRepository(db_session)

    settings_row = repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="llama-3",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-user-1",
    )

    assert settings_row.id == "default"
    assert settings_row.llm_provider == "llama-cpp"
    assert settings_row.llm_url == "http://llama-server:8000/v1"
    assert settings_row.llm_model == "llama-3"
    assert settings_row.embedding_provider is None
    assert settings_row.updated_by == "admin-user-1"


@pytest.mark.unit
def test_upsert_updates_existing_singleton_row(db_session):
    """A second upsert() call updates the same row rather than creating a new one."""
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="llama-3",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-user-1",
    )

    updated = repo.upsert(
        llm_provider="openai-compatible",
        llm_url="http://custom:9000/v1",
        llm_model="gpt-4",
        embedding_provider="llama-cpp",
        embedding_url="http://embedding-server:8000/v1",
        embedding_model="nomic-embed",
        updated_by="admin-user-2",
    )

    all_rows = db_session.query(type(updated)).all()
    assert len(all_rows) == 1
    assert updated.id == "default"
    assert updated.llm_provider == "openai-compatible"
    assert updated.llm_url == "http://custom:9000/v1"
    assert updated.embedding_provider == "llama-cpp"
    assert updated.updated_by == "admin-user-2"


@pytest.mark.unit
def test_get_returns_the_persisted_singleton_row(db_session):
    """get() retrieves the row created by upsert()."""
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="fake",
        llm_url=None,
        llm_model=None,
        embedding_provider="fake",
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-user-1",
    )

    result = repo.get()

    assert result is not None
    assert result.llm_provider == "fake"
    assert result.embedding_provider == "fake"


@pytest.mark.unit
def test_partial_upsert_leaves_other_fields_untouched_when_repeated_with_same_values(db_session):
    """Upserting only LLM fields, then only embedding fields, preserves both
    (the repository always writes the full set of fields it's called with;
    callers pass through unchanged values for fields they don't want to change).
    """
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="llama-3",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-user-1",
    )

    updated = repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="llama-3",
        embedding_provider="llama-cpp",
        embedding_url="http://embedding-server:8000/v1",
        embedding_model="nomic-embed",
        updated_by="admin-user-1",
    )

    assert updated.llm_provider == "llama-cpp"
    assert updated.llm_url == "http://llama-server:8000/v1"
    assert updated.embedding_provider == "llama-cpp"
    assert updated.embedding_model == "nomic-embed"
