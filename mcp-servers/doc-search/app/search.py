"""Core search logic: query embedding + pgvector cosine-similarity search.

Ported from backend/app/agents/tools.py and backend/app/repositories/
embedding_repository.py — same top-k ranking, same excerpt formatting,
same "no matches" message. This is a structural move (search now runs in
this standalone MCP server instead of in-process in the backend), not a
behavior change.
"""

import random
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Embedding, KnowledgeBase, SystemSettings

MAX_EXCERPT_CHARS = 300

# Must match backend/app/services/embedding_service.py's EMBEDDING_DIMENSION —
# nomic-embed-text-v1.5's output dimension (see docs/LLM_SETUP.md). Doc-search
# can't import that constant directly (separate deployable, no shared package),
# so it's duplicated here rather than left as an unnamed literal.
EMBEDDING_DIMENSION = 768


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
        with httpx.Client(timeout=config.timeout) as client:
            response = client.post(
                f"{config.url}/embeddings",
                json={"input": text, "model": config.model},
            )
            response.raise_for_status()
            embedding: list[float] = response.json()["data"][0]["embedding"]
            return embedding
    else:
        raise ValueError(f"Unknown embedding_provider: {config.provider}")


def search_knowledge_base(db: Session, user_id: str, query: str, top_k: int = 5) -> str:
    """Search user_id's knowledge base for documents relevant to query.

    user_id must already have been verified (see app.auth.verify_bearer_token)
    — this function trusts it as given and does not re-derive it, mirroring
    how backend/app/agents/tools.py's tool trusted its closure-bound user_id.

    Returns the title and a content excerpt for each matching document,
    nearest-first by cosine distance, or a message saying nothing matched.
    """
    query_embedding = generate_query_embedding(db, query)

    matches = (
        db.query(
            Embedding,
            KnowledgeBase,
            Embedding.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(KnowledgeBase, Embedding.doc_id == KnowledgeBase.id)
        .filter(
            KnowledgeBase.user_id == user_id,
            Embedding.deleted_at.is_(None),
        )
        .order_by("distance")
        .limit(top_k)
        .all()
    )

    if not matches:
        return "No matching documents were found in the knowledge base."

    excerpts = []
    for _, knowledge_base, _ in matches:
        excerpt = knowledge_base.content[:MAX_EXCERPT_CHARS]
        if len(knowledge_base.content) > MAX_EXCERPT_CHARS:
            excerpt += "..."
        excerpts.append(f"Title: {knowledge_base.title}\n{excerpt}")

    return "\n\n".join(excerpts)
