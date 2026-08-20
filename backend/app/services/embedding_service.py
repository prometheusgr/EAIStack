"""Service for embedding generation and management."""

import random

import httpx

from app.core.config import settings

EMBEDDING_DIMENSION = 768


def generate_embedding(text: str) -> list[float]:
    """Generate an embedding vector for text, via the configured provider.

    Mirrors the chat LLM's provider switch (see app.core.llm_client): the
    "fake" provider (default, used by unit tests) returns a deterministic
    hash-based vector with no semantic meaning. The "llama-cpp" provider
    calls a real llama-server instance running in embedding mode.

    Args:
        text: The text to generate an embedding for.

    Returns:
        A list of 768 floating point values representing the embedding
        (nomic-embed-text-v1.5's output dimension; see docs/LLM_SETUP.md).
    """
    if settings.embedding_provider == "fake":
        return _generate_fake_embedding(text)
    elif settings.embedding_provider == "llama-cpp":
        return _generate_llama_cpp_embedding(text)
    else:
        raise ValueError(f"Unknown embedding_provider: {settings.embedding_provider}")


def _generate_fake_embedding(text: str) -> list[float]:
    """Deterministic mock embedding: same text always produces the same vector."""
    random.seed(hash(text) % (2**32))
    return [random.gauss(0, 0.1) for _ in range(EMBEDDING_DIMENSION)]


def _generate_llama_cpp_embedding(text: str) -> list[float]:
    """Call a llama-server instance running in embedding mode.

    Uses llama-server's OpenAI-compatible /v1/embeddings endpoint
    (`llama-server --embedding`).
    """
    with httpx.Client(timeout=settings.embedding_timeout) as client:
        response = client.post(
            f"{settings.embedding_url}/embeddings",
            json={"input": text, "model": settings.embedding_model},
        )
        response.raise_for_status()
        embedding: list[float] = response.json()["data"][0]["embedding"]
        return embedding
