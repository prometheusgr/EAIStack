"""Service for embedding generation and management."""

import random
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.core.tls import get_ssl_context
from app.services.system_settings_service import EmbeddingConfig, resolve_embedding_config

EMBEDDING_DIMENSION = 768


@dataclass(frozen=True)
class EmbeddingResult:
    """A generated embedding plus the provider/model that produced it.

    Callers that persist the vector (knowledge_base.py) store provider/model
    into Embedding.embed_metadata alongside it. Without this, a runtime
    provider switch (via the Settings screen) would silently mix vectors from
    incompatible models in the same knowledge base with no way to detect it.
    """

    vector: list[float]
    provider: str
    model: str

    def as_embed_metadata(self) -> dict[str, str]:
        """Provenance dict stored in Embedding.embed_metadata by every write site."""
        return {"embedding_provider": self.provider, "embedding_model": self.model}


def generate_embedding(db: Session, text: str) -> EmbeddingResult:
    """Generate an embedding vector for text, via the configured provider.

    Mirrors the chat LLM's provider switch (see app.core.llm_client): the
    "fake" provider (default, used by unit tests) returns a deterministic
    hash-based vector with no semantic meaning. The "llama-cpp" provider
    calls a real llama-server instance running in embedding mode.

    Config is resolved fresh on every call via resolve_embedding_config(db)
    — a DB-stored admin override (if any) wins over the env-var default,
    with no caching, so a change made through the settings screen takes
    effect on the next call without a backend restart.

    Args:
        db: Database session, used to check for a runtime provider override.
        text: The text to generate an embedding for.

    Returns:
        An EmbeddingResult carrying a 768-dimensional vector (nomic-embed-text-v1.5's
        output dimension; see docs/LLM_SETUP.md) plus the provider/model that
        produced it.
    """
    config = resolve_embedding_config(db)

    if config.provider == "fake":
        vector = _generate_fake_embedding(text)
    elif config.provider == "llama-cpp":
        vector = _generate_llama_cpp_embedding(config, text)
    else:
        raise ValueError(f"Unknown embedding_provider: {config.provider}")

    return EmbeddingResult(vector=vector, provider=config.provider, model=config.model)


def _generate_fake_embedding(text: str) -> list[float]:
    """Deterministic mock embedding: same text always produces the same vector."""
    random.seed(hash(text) % (2**32))
    return [random.gauss(0, 0.1) for _ in range(EMBEDDING_DIMENSION)]


def _generate_llama_cpp_embedding(config: EmbeddingConfig, text: str) -> list[float]:
    """Call a llama-server instance running in embedding mode.

    Uses llama-server's OpenAI-compatible /v1/embeddings endpoint
    (`llama-server --embedding`).

    Uses get_ssl_context() (not the raw path) because this runs once per
    document chunk during ingestion — a large document could otherwise
    trigger hundreds of redundant CA bundle PEM parses for one ingest.
    """
    with httpx.Client(timeout=config.timeout, verify=get_ssl_context()) as client:
        response = client.post(
            f"{config.url}/embeddings",
            json={"input": text, "model": config.model},
        )
        response.raise_for_status()
        embedding: list[float] = response.json()["data"][0]["embedding"]
        return embedding
