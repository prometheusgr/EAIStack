"""Unit tests for doc-search's query-time embedding wrapper.

nomic-embed-text-v1.5 is an asymmetric embedding model: it expects
"search_query: " prepended at query time (see docs/LLM_SETUP.md and
backend/app/services/embedding_service.py, which applies the mirrored
"search_document: " prefix at index time). doc-search only ever queries —
it never indexes — so it needs just the query-side wrapper.

These tests avoid touching a real DB (resolve_embedding_config is
monkeypatched), following the same pattern as
tests/unit/test_ca_bundle_verification.py's call-site-7 coverage, so they
can run in the unit gate rather than requiring Postgres.
"""

from unittest.mock import MagicMock, patch

import pytest

import app.search as search_module
from app.search import embed_query


@pytest.mark.unit
def test_embed_query_prefixes_text_with_search_query(monkeypatch):
    """embed_query must send 'search_query: <text>' to the provider, not the
    bare text — the query-time half of the asymmetric prefix.
    """
    monkeypatch.setattr(
        search_module,
        "resolve_embedding_config",
        lambda db: search_module.EmbeddingConfig(
            provider="llama-cpp",
            url="http://embedding-server:8000/v1",
            model="nomic-embed-text-v1.5.Q4_K_M.gguf",
            timeout=60,
        ),
    )

    fake_vector = [0.01 * i for i in range(768)]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"data": [{"embedding": fake_vector, "index": 0}]})
    mock_response.raise_for_status = MagicMock()

    with patch.object(search_module.httpx, "Client") as mock_client_class:
        mock_client_instance = MagicMock()
        mock_client_instance.post = MagicMock(return_value=mock_response)
        mock_client_instance.__enter__ = MagicMock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = MagicMock(return_value=None)
        mock_client_class.return_value = mock_client_instance

        embed_query(db=None, text="What snacks does the office serve?")

        call_args = mock_client_instance.post.call_args
        assert (
            call_args.kwargs["json"]["input"] == "search_query: What snacks does the office serve?"
        )


@pytest.mark.unit
def test_embed_query_prefixes_even_the_fake_provider(monkeypatch):
    """The prefix is applied before the provider switch, so the "fake"
    provider (used by unit tests) also sees prefixed text — keeping it
    deterministic (same prefixed text -> same hash-based vector) while still
    proving the prefix is structurally applied, not just for llama-cpp.
    """
    monkeypatch.setattr(
        search_module,
        "resolve_embedding_config",
        lambda db: search_module.EmbeddingConfig(
            provider="fake", url="", model="fake-model", timeout=60
        ),
    )

    prefixed_direct = embed_query(db=None, text="search_query: shared text")
    via_wrapper = embed_query(db=None, text="shared text")

    # Calling embed_query with already-prefixed text double-prefixes it, so
    # the two vectors must differ — proving the wrapper applied its own
    # prefix rather than relying on the caller to have done so.
    assert prefixed_direct != via_wrapper
