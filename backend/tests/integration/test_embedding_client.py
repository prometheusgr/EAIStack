"""Integration test for the real llama-cpp embedding provider.

Requires a llama-server instance running in embedding mode (see
docs/LLM_SETUP.md) at settings.embedding_url, with settings.embedding_provider
set to "llama-cpp". Not gated by CI — run manually against the real stack.
"""

import pytest

from app.core.config import settings
from app.services.embedding_service import generate_embedding

# These exercise a real embedding server, which is opt-in: the default
# provider is "fake". Skip rather than fail when it isn't configured — a
# suite that is red by default trains everyone to ignore red, and "you did
# not opt in" is not a defect. Set EMBEDDING_PROVIDER=llama-cpp (with a
# reachable EMBEDDING_URL) to run them.
requires_real_embedding_server = pytest.mark.skipif(
    settings.embedding_provider != "llama-cpp",
    reason="Set EMBEDDING_PROVIDER=llama-cpp to run against a real llama-server (docs/LLM_SETUP.md).",
)


@pytest.mark.integration
@requires_real_embedding_server
def test_generate_embedding_against_real_llama_server(db_session):
    """A real embedding server should return a 768-dim vector for real text."""
    result = generate_embedding(
        db_session, "search_document: The office serves pretzels on Fridays."
    )

    assert len(result.vector) == 768
    assert all(isinstance(value, float) for value in result.vector)
    assert result.provider == "llama-cpp"


@pytest.mark.integration
@requires_real_embedding_server
def test_generate_embedding_similar_text_produces_similar_vectors(db_session):
    """A real embedding model should place semantically similar text closer
    together than unrelated text, unlike the fake hash-based provider.
    """

    def cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return dot / (norm_a * norm_b)

    snack_policy = generate_embedding(
        db_session, "search_document: The office serves pretzels on Fridays."
    )
    snack_query = generate_embedding(db_session, "search_query: What snack is served on Fridays?")
    unrelated = generate_embedding(
        db_session, "search_document: The quarterly tax filing deadline is April 15."
    )

    related_similarity = cosine_similarity(snack_policy.vector, snack_query.vector)
    unrelated_similarity = cosine_similarity(snack_policy.vector, unrelated.vector)

    assert related_similarity > unrelated_similarity
