"""TDD tests for the embedding provider switch (fake vs llama-cpp).

Mirrors tests/unit/test_llm_client.py's structure for the chat LLM: verifies
the provider switch picks the right implementation, and that the real path
maps requests/responses correctly against a mocked HTTP boundary. No test
here talks to a real llama-server.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.embedding_service import embed_document, embed_query, generate_embedding


@pytest.fixture
def embedding_provider(monkeypatch):
    """Set settings.embedding_provider for the duration of a single test."""

    def _set(provider: str):
        monkeypatch.setattr(settings, "embedding_provider", provider)

    return _set


@pytest.mark.unit
def test_generate_embedding_fake_provider_is_deterministic(embedding_provider, db_session):
    """The fake provider should return the same vector for the same text."""
    embedding_provider("fake")

    first = generate_embedding(db_session, "What snacks does the office serve?")
    second = generate_embedding(db_session, "What snacks does the office serve?")

    assert first.vector == second.vector


@pytest.mark.unit
def test_generate_embedding_fake_provider_differs_by_text(embedding_provider, db_session):
    """Different input text should produce different fake vectors."""
    embedding_provider("fake")

    first = generate_embedding(db_session, "alpha")
    second = generate_embedding(db_session, "beta")

    assert first.vector != second.vector


@pytest.mark.unit
def test_generate_embedding_fake_provider_dimension(embedding_provider, db_session):
    """The fake provider's output dimension must match the pgvector column (768)."""
    embedding_provider("fake")

    result = generate_embedding(db_session, "some text")

    assert len(result.vector) == 768


@pytest.mark.unit
def test_generate_embedding_result_carries_provider_and_model(embedding_provider, db_session):
    """The result records which provider/model produced the vector, so a
    runtime provider switch is detectable later from stored embed_metadata.
    """
    embedding_provider("fake")

    result = generate_embedding(db_session, "some text")

    assert result.provider == "fake"
    assert result.model == settings.embedding_model


@pytest.mark.unit
def test_generate_embedding_llama_cpp_calls_embeddings_endpoint(
    embedding_provider, monkeypatch, db_session
):
    """The llama-cpp provider should POST to {embedding_url}/embeddings with the text."""
    embedding_provider("llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        result = generate_embedding(db_session, "search_document: office snack policy")

        assert result.vector == fake_vector
        assert result.provider == "llama-cpp"
        assert result.model == "nomic-embed-text-v1.5.Q4_K_M.gguf"
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args.args[0] == "http://localhost:8002/v1/embeddings"
        assert call_args.kwargs["json"]["input"] == "search_document: office snack policy"
        assert call_args.kwargs["json"]["model"] == "nomic-embed-text-v1.5.Q4_K_M.gguf"


@pytest.mark.unit
def test_generate_embedding_llama_cpp_raises_on_http_error(
    embedding_provider, monkeypatch, db_session
):
    """An HTTP error from the embedding server should propagate, not be swallowed."""
    import httpx

    embedding_provider("llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=mock_response
        )
    )

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        with pytest.raises(httpx.HTTPStatusError):
            generate_embedding(db_session, "some text")


@pytest.mark.unit
def test_generate_embedding_rejects_unknown_provider(embedding_provider, db_session):
    """An unrecognized provider should fail loudly, naming the bad value."""
    embedding_provider("not-a-real-provider")

    with pytest.raises(ValueError, match="not-a-real-provider"):
        generate_embedding(db_session, "some text")


@pytest.mark.unit
def test_generate_embedding_uses_db_override_over_env_default(db_session, monkeypatch):
    """A DB-stored provider override changes which embedding backend
    generate_embedding() calls, without any change to settings.embedding_provider —
    the DB row is read fresh on every call, matching the LLM client's behavior.
    """
    assert settings.embedding_provider == "fake"
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    SystemSettingsRepository(db_session).upsert(
        llm_provider=None,
        llm_url=None,
        llm_model=None,
        embedding_provider="llama-cpp",
        embedding_url="http://embedding-server:8000/v1",
        embedding_model="nomic-embed-text-v1.5.Q4_K_M.gguf",
        updated_by="admin-1",
    )
    db_session.commit()

    fake_vector = [0.02 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        result = generate_embedding(db_session, "search_document: office snack policy")

        assert result.vector == fake_vector
        assert result.provider == "llama-cpp"
        call_args = mock_client_instance.post.call_args
        assert call_args.args[0] == "http://embedding-server:8000/v1/embeddings"


# embed_document / embed_query: nomic-embed-text-v1.5 is an asymmetric
# embedding model that expects "search_document: " at index time and
# "search_query: " at query time (see docs/LLM_SETUP.md). These wrappers
# make the prefix structural — tied to the caller's *purpose*, not a flag
# that can be passed wrong — so every production call site goes through one
# of the two rather than remembering to prepend text itself.


@pytest.mark.unit
def test_embed_document_prefixes_text_with_search_document(monkeypatch, db_session):
    """embed_document must send 'search_document: <text>' to the provider,
    not the bare text — this is the index-time half of the asymmetric prefix.
    """
    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        embed_document(db_session, "office snack policy")

        call_args = mock_client_instance.post.call_args
        assert call_args.kwargs["json"]["input"] == "search_document: office snack policy"


@pytest.mark.unit
def test_embed_query_prefixes_text_with_search_query(monkeypatch, db_session):
    """embed_query must send 'search_query: <text>' to the provider — the
    query-time half of the asymmetric prefix.
    """
    monkeypatch.setattr(settings, "embedding_provider", "llama-cpp")
    monkeypatch.setattr(settings, "embedding_url", "http://localhost:8002/v1")
    monkeypatch.setattr(settings, "embedding_model", "nomic-embed-text-v1.5.Q4_K_M.gguf")

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.embedding_service.httpx.Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        embed_query(db_session, "What snacks does the office serve?")

        call_args = mock_client_instance.post.call_args
        assert (
            call_args.kwargs["json"]["input"] == "search_query: What snacks does the office serve?"
        )


@pytest.mark.unit
def test_embed_document_and_embed_query_prefix_even_the_fake_provider(
    embedding_provider, db_session
):
    """The prefix is applied before the provider switch, so even the "fake"
    provider (used by unit tests) sees prefixed text. This keeps the fake
    provider deterministic (same prefixed text -> same hash-based vector)
    while still exercising the real structural behavior in tests that use
    embed_document/embed_query directly, rather than only in llama-cpp tests.
    """
    embedding_provider("fake")

    doc_result = embed_document(db_session, "shared text")
    query_result = embed_query(db_session, "shared text")

    # Same underlying text, different prefixes -> different fake vectors,
    # proving the prefix (not just the text) reached the provider.
    assert doc_result.vector != query_result.vector


@pytest.mark.unit
def test_embed_document_result_carries_provider_and_model(embedding_provider, db_session):
    """embed_document still returns an EmbeddingResult with provenance, same
    as generate_embedding, so write sites can tag Embedding.embed_metadata.
    """
    embedding_provider("fake")

    result = embed_document(db_session, "some text")

    assert result.provider == "fake"
    assert result.model == settings.embedding_model
