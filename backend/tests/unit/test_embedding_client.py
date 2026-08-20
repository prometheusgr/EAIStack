"""TDD tests for the embedding provider switch (fake vs llama-cpp).

Mirrors tests/unit/test_llm_client.py's structure for the chat LLM: verifies
the provider switch picks the right implementation, and that the real path
maps requests/responses correctly against a mocked HTTP boundary. No test
here talks to a real llama-server.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services.embedding_service import generate_embedding


@pytest.fixture
def embedding_provider(monkeypatch):
    """Set settings.embedding_provider for the duration of a single test."""

    def _set(provider: str):
        monkeypatch.setattr(settings, "embedding_provider", provider)

    return _set


@pytest.mark.unit
def test_generate_embedding_fake_provider_is_deterministic(embedding_provider):
    """The fake provider should return the same vector for the same text."""
    embedding_provider("fake")

    first = generate_embedding("What snacks does the office serve?")
    second = generate_embedding("What snacks does the office serve?")

    assert first == second


@pytest.mark.unit
def test_generate_embedding_fake_provider_differs_by_text(embedding_provider):
    """Different input text should produce different fake vectors."""
    embedding_provider("fake")

    first = generate_embedding("alpha")
    second = generate_embedding("beta")

    assert first != second


@pytest.mark.unit
def test_generate_embedding_fake_provider_dimension(embedding_provider):
    """The fake provider's output dimension must match the pgvector column (768)."""
    embedding_provider("fake")

    result = generate_embedding("some text")

    assert len(result) == 768


@pytest.mark.unit
def test_generate_embedding_llama_cpp_calls_embeddings_endpoint(embedding_provider, monkeypatch):
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

        result = generate_embedding("search_document: office snack policy")

        assert result == fake_vector
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args.args[0] == "http://localhost:8002/v1/embeddings"
        assert call_args.kwargs["json"]["input"] == "search_document: office snack policy"
        assert call_args.kwargs["json"]["model"] == "nomic-embed-text-v1.5.Q4_K_M.gguf"


@pytest.mark.unit
def test_generate_embedding_llama_cpp_raises_on_http_error(embedding_provider, monkeypatch):
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
            generate_embedding("some text")


@pytest.mark.unit
def test_generate_embedding_rejects_unknown_provider(embedding_provider):
    """An unrecognized provider should fail loudly, naming the bad value."""
    embedding_provider("not-a-real-provider")

    with pytest.raises(ValueError, match="not-a-real-provider"):
        generate_embedding("some text")
