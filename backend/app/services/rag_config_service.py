"""RAG retrieval/chunking config resolution: DB override over env default.

Resolves the effective retrieval/chunking policy the same way
guardrail_config_service and rate_limit_config_service resolve their
config - DB value if a row set it, else the env default, read fresh on
every call so an admin's change (via the settings screen) takes effect on
the next chat/search request with no backend restart.

backend/app/services/chunking_service.py and
backend/app/repositories/embedding_repository.py stay pure, DB-free
modules that accept plain values as parameters - this service is the one
place that reads SystemSettings and turns it into those values. doc-search
(a separate deployable) has its own, independent copy of this resolution
for the subset of fields it needs at query time - see
mcp-servers/doc-search/app/search.py's resolve_rag_config.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import SystemSettings
from app.repositories.system_settings_repository import SystemSettingsRepository
from app.services.config_resolution import resolve_field
from app.services.system_settings_service import NOT_PROVIDED, NotProvided


@dataclass(frozen=True)
class RagConfig:
    """Effective RAG retrieval/chunking policy, DB override merged over env
    defaults.

    similarity_threshold is a cosine-distance cutoff, not a similarity
    score: smaller distance means more similar, so a match is kept when its
    distance is below this value. None means no cutoff (today's behavior);
    0.0 is a valid, deliberately strict override - resolution must test
    `is not None` rather than truthiness, the same trap every other
    nullable config field in this codebase guards against (see AGENTS.md's
    Retention Field Semantics).

    min_chunk_size and chunk_size are independent, both admin-facing
    (rather than one derived from the other) - callers must not assume
    min_chunk_size < chunk_size without checking, since this dataclass
    itself does not re-validate the ordering. That ordering is enforced at
    write time (app.api.settings, on every PUT) and at the env-default
    layer (app.core.config.Settings's own model validator), not re-checked
    here on every read.
    """

    similarity_threshold: float | None
    max_results: int
    min_chunk_size: int
    chunk_size: int
    chunk_overlap_ratio: float
    max_excerpt_chars: int


def resolve_rag_config(
    db: Session, db_settings: SystemSettings | None | NotProvided = NOT_PROVIDED
) -> RagConfig:
    """Resolve the effective RAG retrieval/chunking policy: DB value if set,
    else env default, for every field.

    db_settings: the already-fetched singleton row, if the caller has one
    (see app.api.settings._to_response, which resolves provider, retention,
    guardrail, tracing, rate-limit, and RAG config from the same row) -
    avoids a redundant SELECT. Omit it for callers that only have a
    session.
    """
    if db_settings is NOT_PROVIDED:
        db_settings = SystemSettingsRepository(db).get()

    return RagConfig(
        similarity_threshold=resolve_field(
            db_value=db_settings.rag_similarity_threshold if db_settings else None,
            env_default=settings.rag_similarity_threshold,
        ),
        max_results=resolve_field(
            db_value=db_settings.rag_max_results if db_settings else None,
            env_default=settings.rag_max_results,
        ),
        min_chunk_size=resolve_field(
            db_value=db_settings.rag_min_chunk_size if db_settings else None,
            env_default=settings.rag_min_chunk_size,
        ),
        chunk_size=resolve_field(
            db_value=db_settings.rag_chunk_size if db_settings else None,
            env_default=settings.rag_chunk_size,
        ),
        chunk_overlap_ratio=resolve_field(
            db_value=db_settings.rag_chunk_overlap_ratio if db_settings else None,
            env_default=settings.rag_chunk_overlap_ratio,
        ),
        max_excerpt_chars=resolve_field(
            db_value=db_settings.rag_max_excerpt_chars if db_settings else None,
            env_default=settings.rag_max_excerpt_chars,
        ),
    )
