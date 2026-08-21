"""TDD tests for system_settings_service: resolving effective LLM/embedding
config (DB override, falling back to env-var settings) and the fixed list
of provider options the settings screen offers.
"""

import pytest

from app.core.config import settings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.system_settings_service import (
    available_provider_options,
    resolve_embedding_config,
    resolve_llm_config,
)


@pytest.mark.unit
def test_resolve_llm_config_falls_back_to_env_settings_when_no_db_row(db_session):
    """With no SystemSettings row at all, every field comes from env settings."""
    config = resolve_llm_config(db_session)

    assert config.provider == settings.llm_provider
    assert config.url == settings.llm_url
    assert config.model == settings.llm_model
    assert config.api_key == settings.llm_api_key
    assert config.timeout == settings.llm_timeout


@pytest.mark.unit
def test_resolve_llm_config_uses_db_override_when_present(db_session):
    """A DB row with non-null LLM fields overrides the env-var defaults."""
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="custom-model",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_llm_config(db_session)

    assert config.provider == "llama-cpp"
    assert config.url == "http://llama-server:8000/v1"
    assert config.model == "custom-model"


@pytest.mark.unit
def test_resolve_llm_config_api_key_and_timeout_always_come_from_env(db_session):
    """api_key and timeout are never DB-overridable — no such columns exist,
    and they must never be exposed to the settings screen (see security note
    in app.api.settings).
    """
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="llama-cpp",
        llm_url="http://llama-server:8000/v1",
        llm_model="custom-model",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_llm_config(db_session)

    assert config.api_key == settings.llm_api_key
    assert config.timeout == settings.llm_timeout


@pytest.mark.unit
def test_resolve_llm_config_falls_back_per_field_when_only_some_are_null(db_session):
    """A DB row can override just the provider and leave url/model NULL,
    each falling back to env independently (not all-or-nothing per row).
    """
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="llama-cpp",
        llm_url=None,
        llm_model=None,
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_llm_config(db_session)

    assert config.provider == "llama-cpp"
    assert config.url == settings.llm_url
    assert config.model == settings.llm_model


@pytest.mark.unit
def test_resolve_llm_config_treats_empty_string_db_value_as_a_real_override(db_session):
    """An empty-string DB column is a deliberate override (e.g. the 'fake'
    provider's URL template is ""), not an unset field. It must resolve to
    "" rather than silently falling back to the env default.
    """
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider="fake",
        llm_url="",
        llm_model="",
        embedding_provider=None,
        embedding_url=None,
        embedding_model=None,
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_llm_config(db_session)

    assert config.url == ""
    assert config.model == ""


@pytest.mark.unit
def test_resolve_embedding_config_falls_back_to_env_settings_when_no_db_row(db_session):
    """With no SystemSettings row at all, every field comes from env settings."""
    config = resolve_embedding_config(db_session)

    assert config.provider == settings.embedding_provider
    assert config.url == settings.embedding_url
    assert config.model == settings.embedding_model
    assert config.timeout == settings.embedding_timeout


@pytest.mark.unit
def test_resolve_embedding_config_uses_db_override_when_present(db_session):
    """A DB row with non-null embedding fields overrides the env-var defaults."""
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider=None,
        llm_url=None,
        llm_model=None,
        embedding_provider="llama-cpp",
        embedding_url="http://embedding-server:8000/v1",
        embedding_model="nomic-embed-text-v1.5.Q4_K_M.gguf",
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.provider == "llama-cpp"
    assert config.url == "http://embedding-server:8000/v1"
    assert config.model == "nomic-embed-text-v1.5.Q4_K_M.gguf"


@pytest.mark.unit
def test_resolve_embedding_config_treats_empty_string_db_value_as_a_real_override(db_session):
    """Same empty-string-is-a-real-override semantics apply to embedding
    fields as to LLM fields.
    """
    repo = SystemSettingsRepository(db_session)
    repo.upsert(
        llm_provider=None,
        llm_url=None,
        llm_model=None,
        embedding_provider="fake",
        embedding_url="",
        embedding_model="",
        updated_by="admin-1",
    )
    db_session.commit()

    config = resolve_embedding_config(db_session)

    assert config.url == ""
    assert config.model == ""


@pytest.mark.unit
def test_available_provider_options_returns_fixed_detected_services():
    """The option list is hardcoded to match docker-compose.yml's service DNS
    names/ports, not discovered dynamically (there's no service-discovery
    mechanism in this stack).
    """
    options = available_provider_options()

    assert "llm" in options
    assert "embedding" in options

    llm_providers = {option["provider"] for option in options["llm"]}
    assert llm_providers == {"fake", "llama-cpp", "openai-compatible"}

    embedding_providers = {option["provider"] for option in options["embedding"]}
    assert embedding_providers == {"fake", "llama-cpp"}

    llama_cpp_llm = next(o for o in options["llm"] if o["provider"] == "llama-cpp")
    assert llama_cpp_llm["url"] == "http://llama-server:8000/v1"

    llama_cpp_embedding = next(o for o in options["embedding"] if o["provider"] == "llama-cpp")
    assert llama_cpp_embedding["url"] == "http://embedding-server:8000/v1"

    openai_compatible = next(o for o in options["llm"] if o["provider"] == "openai-compatible")
    assert openai_compatible["url"] == ""


@pytest.mark.unit
def test_available_provider_options_flags_requires_manual_entry_explicitly():
    """The settings screen must not infer "does this provider need a
    custom URL/model" from an empty-string url convention (that conflates
    "no default URL, but a custom one may be entered" with "not
    customizable"). Each option carries an explicit flag instead.

    fake: no URL, and none is expected (mocked provider) -> not manual entry.
    llama-cpp: has a detected default URL, but an admin can still override it
    with a custom URL/model -> manual entry allowed.
    openai-compatible: no default URL, always requires one -> manual entry.
    """
    options = available_provider_options()

    fake_llm = next(o for o in options["llm"] if o["provider"] == "fake")
    assert fake_llm["requires_manual_entry"] is False

    llama_cpp_llm = next(o for o in options["llm"] if o["provider"] == "llama-cpp")
    assert llama_cpp_llm["requires_manual_entry"] is True

    openai_compatible = next(o for o in options["llm"] if o["provider"] == "openai-compatible")
    assert openai_compatible["requires_manual_entry"] is True

    fake_embedding = next(o for o in options["embedding"] if o["provider"] == "fake")
    assert fake_embedding["requires_manual_entry"] is False

    llama_cpp_embedding = next(o for o in options["embedding"] if o["provider"] == "llama-cpp")
    assert llama_cpp_embedding["requires_manual_entry"] is True
