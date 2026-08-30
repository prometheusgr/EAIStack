"""Core search logic: query embedding + result formatting.

Ported from backend/app/agents/tools.py — same top-k ranking, same excerpt
formatting, same "no matches" message. This is a structural move (search now
runs in this standalone MCP server instead of in-process in the backend),
not a behavior change.

The pgvector query itself lives in app/repositories/embedding_repository.py,
mirroring the backend's split: this module owns formatting and provider
config, the repository owns data access and the user-isolation filter.
"""

import random
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Embedding, KnowledgeBase, SystemSettings
from app.repositories import EmbeddingRepository
from app.tls import get_ssl_context

MAX_EXCERPT_CHARS = 2000

# Now that content is chunked before storage (see backend/app/services/
# chunking_service.py), a chunk is already passage-sized — this cap is a
# safety net against a single oversized chunk (e.g. an atomic fenced code
# block bigger than the chunking target), not the primary excerpting
# mechanism the old whole-document flow relied on.

# Deduplicating to one chunk per document needs a candidate pool wider than
# top_k (a document can occupy several of the nearest-ranked rows, via its
# other chunks), or dedup could return fewer than top_k distinct documents
# even when more exist. EmbeddingRepository.search_hybrid already fetches a
# generous per-branch candidate margin of its own (_CANDIDATE_MULTIPLIER, in
# app.repositories.embedding_repository) for RRF fusion quality — asking it
# for that pool via return_candidates=True, rather than re-multiplying top_k
# here ourselves, means dedup headroom comes from the repository's existing
# margin instead of compounding a second one on top of it.

# nomic-embed-text-v1.5 is an asymmetric embedding model (see
# docs/LLM_SETUP.md and backend/app/services/embedding_service.py, which
# applies the mirrored "search_document: " prefix at index time): it expects
# "search_query: " prepended to query-time text. doc-search never indexes,
# only queries, so it needs just this one prefix constant. Kept as its own
# duplicate here (not imported from backend) for the same reason as this
# module's EMBEDDING_DIMENSION and app.auth's JWKS verification: doc-search
# is a separate deployable and cannot import from backend/.
_QUERY_PREFIX = "search_query: "

# Must match backend/app/services/embedding_service.py's EMBEDDING_DIMENSION —
# nomic-embed-text-v1.5's output dimension (see docs/LLM_SETUP.md). Doc-search
# can't import that constant directly (separate deployable, no shared package),
# so it's duplicated here rather than left as an unnamed literal.
EMBEDDING_DIMENSION = 768


@dataclass(frozen=True)
class SourceMatch:
    """One document that grounded a search_knowledge_base_with_sources call.

    Structured provenance for a matching document — knowledge_base_id/title/
    heading_path, the same fields already baked into the rendered result's
    prose "Title: ..." / "Section: ..." lines — kept separate from that text
    so a caller (the backend's MCP client) can carry it as data instead of
    parsing it back out of a string meant for the LLM to read.
    """

    knowledge_base_id: str
    title: str
    heading_path: str | None


@dataclass(frozen=True)
class SearchResultWithSources:
    """search_knowledge_base_with_sources's return value: the rendered
    title/heading-path/excerpt text for the LLM to read, plus the
    structured sources it was built from.
    """

    text: str
    sources: list[SourceMatch]


@dataclass(frozen=True)
class EmbeddingConfig:
    """Effective embedding config for one call, DB override merged over env defaults."""

    provider: str
    url: str
    model: str
    timeout: int


def _resolve_field(db_value: str | None, env_default: str) -> str:
    """Resolve one overridable field: the DB value if a row set it, else the
    env default. Mirrors backend/app/services/system_settings_service.py's
    _resolve_field exactly, including the is-not-None (not truthiness) check
    — an empty-string DB override (e.g. the "fake" provider's URL) must not
    be discarded in favor of the env default.
    """
    return db_value if db_value is not None else env_default


def resolve_embedding_config(db: Session) -> EmbeddingConfig:
    """Resolve the effective embedding config, reading the same system_settings
    row the backend's resolve_embedding_config reads — this is what keeps an
    admin's runtime provider switch honored identically by indexing (backend)
    and querying (doc-search) the moment it's saved, rather than doc-search
    silently querying with a stale provider until redeployed.
    """
    db_settings = db.query(SystemSettings).filter(SystemSettings.id == "default").first()

    return EmbeddingConfig(
        provider=_resolve_field(
            db_settings.embedding_provider if db_settings else None, settings.embedding_provider
        ),
        url=_resolve_field(
            db_settings.embedding_url if db_settings else None, settings.embedding_url
        ),
        model=_resolve_field(
            db_settings.embedding_model if db_settings else None, settings.embedding_model
        ),
        timeout=settings.embedding_timeout,
    )


def generate_query_embedding(db: Session, text: str) -> list[float]:
    """Generate an embedding vector for a query, via the configured provider.

    Mirrors backend/app/services/embedding_service.py's provider switch.
    Only "fake" and "llama-cpp" are needed here (doc-search never talks to
    the chat LLM, only the embedding server), matching the subset of
    providers backend/app/core/config.py defines for embeddings.
    """
    config = resolve_embedding_config(db)

    if config.provider == "fake":
        random.seed(hash(text) % (2**32))
        return [random.gauss(0, 0.1) for _ in range(EMBEDDING_DIMENSION)]
    elif config.provider == "llama-cpp":
        # get_ssl_context() (not the raw path) because this runs on every
        # knowledge-base query — reusing the cached, already-parsed trust
        # store avoids re-reading the CA bundle PEM file from disk each time.
        with httpx.Client(timeout=config.timeout, verify=get_ssl_context()) as client:
            response = client.post(
                f"{config.url}/embeddings",
                json={"input": text, "model": config.model},
            )
            response.raise_for_status()
            embedding: list[float] = response.json()["data"][0]["embedding"]
            return embedding
    else:
        raise ValueError(f"Unknown embedding_provider: {config.provider}")


def embed_query(db: Session, text: str) -> list[float]:
    """Generate an embedding for a search query, with the "search_query: "
    prefix nomic-embed-text-v1.5 requires at query time.

    Every query-time call site in this service must go through this
    function rather than generate_query_embedding directly, so the prefix
    is structural rather than left for each call site to remember.
    """
    return generate_query_embedding(db, _QUERY_PREFIX + text)


def search_knowledge_base_with_sources(
    db: Session, user_id: str, query: str, top_k: int = 5
) -> SearchResultWithSources:
    """Search user_id's knowledge base for passages relevant to query.

    user_id must already have been verified (see app.auth.verify_bearer_token)
    — this function trusts it as given and does not re-derive it, mirroring
    how backend/app/agents/tools.py's tool trusted its closure-bound user_id.

    Returns the rendered title/heading-path/excerpt text for up to top_k
    distinct documents (ranked by search_hybrid's fused vector + full-text
    score — see app.repositories.embedding_repository, issue #7 Prompt 3),
    alongside each match's structured provenance (knowledge_base_id/title/
    heading_path — see issue #19), or a "no matches" message with an empty
    sources list. Deduplicated to the single highest-ranked chunk per
    document (see _deduplicate_by_document) so one document's many chunks
    can't crowd out other documents in the result.
    """
    query_embedding = embed_query(db, query)

    repo = EmbeddingRepository(db)
    candidates = repo.search_hybrid(
        user_id, query_embedding, query_text=query, top_k=top_k, return_candidates=True
    )

    if not candidates:
        return SearchResultWithSources(
            text="No matching documents were found in the knowledge base.", sources=[]
        )

    matches = _deduplicate_by_document(candidates)[:top_k]

    excerpts = []
    sources = []
    for embedding, knowledge_base, _ in matches:
        excerpt = embedding.chunk_text[:MAX_EXCERPT_CHARS]
        if len(embedding.chunk_text) > MAX_EXCERPT_CHARS:
            excerpt += "..."

        header = f"Title: {knowledge_base.title}"
        if embedding.heading_path is not None:
            header += f"\nSection: {embedding.heading_path}"
        excerpts.append(f"{header}\n{excerpt}")

        sources.append(
            SourceMatch(
                knowledge_base_id=knowledge_base.id,
                title=knowledge_base.title,
                heading_path=embedding.heading_path,
            )
        )

    return SearchResultWithSources(text="\n\n".join(excerpts), sources=sources)


def _deduplicate_by_document(
    candidates: list[tuple[Embedding, KnowledgeBase, float]],
) -> list[tuple[Embedding, KnowledgeBase, float]]:
    """Keep only the first (nearest, since candidates arrive nearest-first)
    chunk per doc_id, preserving overall rank order.
    """
    seen_doc_ids: set[str] = set()
    deduplicated = []
    for candidate in candidates:
        embedding, _, _ = candidate
        if embedding.doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(embedding.doc_id)
        deduplicated.append(candidate)

    return deduplicated
