"""Unit tests for RAG retrieval/chunking config resolution - TDD discipline.

Mirrors test_rate_limit_config_service.py's config-resolution scenarios: DB
override over env default, resolved fresh per call, and `is not None`
(never truthiness) semantics per AGENTS.md's Retention Field Semantics
section - relevant here for rag_similarity_threshold, where 0.0 is a valid,
strict override distinct from "no cutoff" (None).
"""

import pytest

from app.core.config import settings
from app.db.models import SystemSettings
from app.services.rag_config_service import RagConfig, resolve_rag_config


@pytest.mark.unit
def test_resolve_rag_config_falls_back_to_env_defaults_when_no_db_row(db_session):
    """With no SystemSettings row, RAG config comes from env-level config."""
    config = resolve_rag_config(db_session)

    assert config.similarity_threshold == settings.rag_similarity_threshold
    assert config.max_results == settings.rag_max_results
    assert config.min_chunk_size == settings.rag_min_chunk_size
    assert config.chunk_size == settings.rag_chunk_size
    assert config.chunk_overlap_ratio == settings.rag_chunk_overlap_ratio
    assert config.max_excerpt_chars == settings.rag_max_excerpt_chars


@pytest.mark.parametrize(
    "db_value,expected",
    [
        (None, settings.rag_similarity_threshold),  # falls back to the env default
        (0.0, 0.0),  # explicit 0.0 override must be honoured, not treated as unset
        (0.35, 0.35),
    ],
)
@pytest.mark.unit
def test_resolve_rag_config_similarity_threshold_is_not_none_semantics(
    db_session, db_value, expected
):
    """0.0 is a meaningful override ("reject everything, even a perfect
    match") just as much as any other explicit value - a truthiness check
    would silently discard an explicit 0.0 the same way it would for
    conversation_retention_hours=0.
    """
    db_session.add(
        SystemSettings(id="default", rag_similarity_threshold=db_value, updated_by="admin-1")
    )
    db_session.commit()

    config = resolve_rag_config(db_session)

    assert config.similarity_threshold == expected


@pytest.mark.unit
def test_resolve_rag_config_db_override_wins_over_env_default(db_session):
    """A DB override for every RAG field wins over its env default - the
    same DB-over-env precedence every other resolver in this codebase uses.
    """
    db_session.add(
        SystemSettings(
            id="default",
            rag_similarity_threshold=0.4,
            rag_max_results=3,
            rag_min_chunk_size=100,
            rag_chunk_size=400,
            rag_chunk_overlap_ratio=0.2,
            rag_max_excerpt_chars=1000,
            updated_by="admin-1",
        )
    )
    db_session.commit()

    config = resolve_rag_config(db_session)

    assert config.similarity_threshold == 0.4
    assert config.max_results == 3
    assert config.min_chunk_size == 100
    assert config.chunk_size == 400
    assert config.chunk_overlap_ratio == 0.2
    assert config.max_excerpt_chars == 1000


@pytest.mark.unit
def test_resolve_rag_config_returns_frozen_dataclass(db_session):
    """RagConfig mirrors RateLimitConfig/GuardrailConfig's shape: a frozen
    dataclass, not a mutable object callers could accidentally mutate.
    """
    config = resolve_rag_config(db_session)

    assert isinstance(config, RagConfig)
    with pytest.raises(Exception):
        config.max_results = 1  # type: ignore[misc]
