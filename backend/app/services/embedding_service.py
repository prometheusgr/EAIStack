"""Service for embedding generation and management."""

import random
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.core.tls import get_ssl_context
from app.db.models import Embedding, KnowledgeBase
from app.services.chunking_service import chunk_document
from app.services.system_settings_service import EmbeddingConfig, resolve_embedding_config

EMBEDDING_DIMENSION = 768

# nomic-embed-text-v1.5 is an asymmetric embedding model (see
# docs/LLM_SETUP.md): it expects different prefixes on text embedded to be
# stored versus text embedded to search, so a stored document and a query
# about it land close together in vector space. The prefix is a property of
# *this model*, not of every embedding provider (the "fake" provider has no
# such requirement), so it is applied here, in the wrapper functions below,
# rather than inside generate_embedding's provider switch.
_DOCUMENT_PREFIX = "search_document: "
_QUERY_PREFIX = "search_query: "


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


def embed_document(db: Session, text: str) -> EmbeddingResult:
    """Generate an embedding for text being indexed (stored) into the
    knowledge base.

    Every index-time call site must go through this function rather than
    generate_embedding directly, so the "search_document: " prefix
    nomic-embed-text-v1.5 requires (see EMBEDDING_DIMENSION's comment above)
    is applied structurally - tied to the caller's *purpose* - instead of
    left for each call site to remember to pass.
    """
    return generate_embedding(db, _DOCUMENT_PREFIX + text)


def embed_documents(db: Session, texts: list[str]) -> list[EmbeddingResult]:
    """Batch variant of embed_document: one provider call for many chunks,
    in the same order as `texts`.

    generate_and_attach_embeddings uses this rather than calling
    embed_document once per chunk - a document that chunks into N passages
    would otherwise make N sequential blocking HTTP round-trips to the
    embedding server, when the OpenAI-compatible /v1/embeddings endpoint
    llama-server exposes (see _generate_llama_cpp_embeddings_batch) already
    accepts a list of inputs in one request.

    Returns [] for an empty list without resolving provider config or
    making a call - chunk_document never returns zero chunks for non-empty
    content, but a batch API should not assume its caller never passes an
    empty list.
    """
    if not texts:
        return []

    config = resolve_embedding_config(db)
    prefixed_texts = [_DOCUMENT_PREFIX + text for text in texts]

    if config.provider == "fake":
        vectors = [_generate_fake_embedding(text) for text in prefixed_texts]
    elif config.provider == "llama-cpp":
        vectors = _generate_llama_cpp_embeddings_batch(config, prefixed_texts)
    else:
        raise ValueError(f"Unknown embedding_provider: {config.provider}")

    return [
        EmbeddingResult(vector=vector, provider=config.provider, model=config.model)
        for vector in vectors
    ]


def embed_query(db: Session, text: str) -> EmbeddingResult:
    """Generate an embedding for a search query against the knowledge base.

    Mirrors embed_document for the query-time half of the asymmetric prefix
    requirement. Every query-time call site must go through this function
    rather than generate_embedding directly.
    """
    return generate_embedding(db, _QUERY_PREFIX + text)


def generate_and_attach_embeddings(db: Session, kb: KnowledgeBase, text: str) -> None:
    """Chunk `text` (see app.services.chunking_service) and stage one
    Embedding row per chunk for insert alongside `kb`.

    Shared by both knowledge-base creation paths (paste-text and
    file-upload; see app.api.knowledge_base) - each tags
    Embedding.embed_metadata with the provider/model that produced the
    vector, so a later runtime provider switch (Settings screen) is
    detectable instead of silently mixing incompatible vectors in the same
    knowledge base. Does not commit; the caller owns the transaction.

    Each chunk is embedded via embed_documents on its own embed_text (title
    + heading path + chunk text), not the bare chunk text - a chunk
    extracted from its section loses the context that makes it meaningful
    otherwise (see chunking_service.Chunk.embed_text). All chunks are
    embedded in a single batch call rather than one call per chunk (see
    embed_documents), so a document with many chunks costs one round trip
    to the embedding server, not N.
    """
    chunks = chunk_document(text, title=kb.title)
    embedding_results = embed_documents(db, [chunk.embed_text for chunk in chunks])

    for chunk, embedding_result in zip(chunks, embedding_results):
        embedding = Embedding(
            id=str(uuid4()),
            doc_id=kb.id,
            embedding=embedding_result.vector,
            embed_metadata=embedding_result.as_embed_metadata(),
            chunk_index=chunk.chunk_index,
            chunk_text=chunk.text,
            heading_path=chunk.heading_path,
        )
        db.add(embedding)


def replace_embeddings(db: Session, kb: KnowledgeBase, text: str, *, now: datetime) -> None:
    """Soft-delete kb's existing Embedding rows and stage fresh chunked
    rows for its new content.

    Used by the update path (app.api.knowledge_base.update_knowledge_base):
    edited content can chunk into a different number of passages than the
    original, so an in-place update of a single row (the pre-chunking
    behavior) no longer makes sense - the old chunk set is replaced
    wholesale, the same soft-delete convention
    KnowledgeBaseRepository.soft_delete_with_embeddings already uses for a
    deleted document. Does not commit; the caller owns the transaction.

    now is accepted rather than read via datetime.now() internally, per
    AGENTS.md's time-injection pattern (see docs/TIME_INJECTION.md) - the
    same pattern app.services.retention_service's functions follow, so the
    exact soft-delete timestamp is testable without monkeypatching datetime.

    The soft-delete is a single bulk UPDATE rather than a SELECT-then-mutate
    loop: the old rows' full contents (including each chunk's 768-dim
    vector and chunk_text) are never needed here, only overwritten, so
    fetching them into Python first would be wasted I/O that scales with
    chunk count on every content edit.
    """
    db.query(Embedding).filter(Embedding.doc_id == kb.id, Embedding.deleted_at.is_(None)).update(
        {"deleted_at": now}
    )

    generate_and_attach_embeddings(db, kb, text)


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


def _generate_llama_cpp_embeddings_batch(
    config: EmbeddingConfig, texts: list[str]
) -> list[list[float]]:
    """Call llama-server's /v1/embeddings endpoint once for many texts.

    The OpenAI-compatible endpoint accepts `input` as a list, returning one
    `data` entry per input tagged with its own `index` - responses are not
    guaranteed to arrive in request order, so results are sorted by that
    index before being returned, keeping the output order matched to
    `texts`' order the same way a caller would expect from N individual
    calls.
    """
    with httpx.Client(timeout=config.timeout, verify=get_ssl_context()) as client:
        response = client.post(
            f"{config.url}/embeddings",
            json={"input": texts, "model": config.model},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda entry: entry["index"])
        return [entry["embedding"] for entry in data]
