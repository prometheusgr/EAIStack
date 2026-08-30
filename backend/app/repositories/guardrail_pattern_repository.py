"""Repository for GuardrailPattern data access."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import GuardrailPattern

_BUILT_IN_SOURCE = "built_in"
_CUSTOM_SOURCE = "custom"


class GuardrailPatternRepository:
    """Repository for the input guardrail's toggleable pattern list.

    Unlike EmbeddingRepository or KnowledgeBaseRepository, methods here take
    no user_id: guardrail patterns are system-wide, admin-managed config
    (see the GuardrailPattern model docstring), not per-tenant data, the
    same posture as SystemSettingsRepository.
    """

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def list_all(self) -> list[GuardrailPattern]:
        """Fetch every pattern row, built-in and custom alike, ordered by id
        for a stable, deterministic list across requests -- without this,
        the Settings screen's pattern checklist can visibly reorder between
        page loads, since Postgres makes no ordering guarantee otherwise.
        """
        return self.db.query(GuardrailPattern).order_by(GuardrailPattern.id).all()

    def get(self, pattern_id: str) -> GuardrailPattern | None:
        """Fetch one pattern row by id, or None if it doesn't exist."""
        return self.db.query(GuardrailPattern).filter(GuardrailPattern.id == pattern_id).first()

    def ensure_built_ins_seeded(self, built_ins: dict[str, str]) -> None:
        """Insert a built_in row (pattern_text=None, enabled=True) for any id
        in built_ins not already present in the table.

        Idempotent and safe to call on every config resolution (see
        app.services.guardrail_config_service.resolve_guardrail_config): an
        id already present is left untouched, including its enabled state,
        so an admin's toggle is never reset by a later seeding call. This is
        also how a future code change that adds another built-in pattern
        (a new key in built_ins) appears in the DB automatically, with no
        migration or backfill script needed.

        Concurrency: this is a read-then-insert, not an atomic upsert, so
        two overlapping calls against a still-unseeded table (e.g. two
        concurrent chat requests hitting a freshly migrated database) can
        both decide the same missing id needs inserting. Rather than an
        `INSERT ... ON CONFLICT` (Postgres-specific, and this repo's unit
        tests run against SQLite -- see Embedding.chunk_text_search's
        docstring for why that constraint already shapes this codebase),
        each insert runs in its own SAVEPOINT (`Session.begin_nested`) and a
        duplicate-key IntegrityError is caught and treated as "another
        caller already seeded this row" rather than a real failure: the row
        exists either way, which is all this method promises. A SAVEPOINT
        (not a plain db.rollback()) matters here specifically because the
        caller may already have other, unrelated flushed-but-uncommitted
        work in the same session (e.g. an audit-log write earlier in the
        same request) -- rolling back the whole transaction to recover from
        one duplicate insert would discard that work too.

        Does not commit; the caller owns the transaction.
        """
        existing_ids = self._existing_built_in_ids(built_ins.keys())

        for pattern_id, label in built_ins.items():
            if pattern_id in existing_ids:
                continue
            try:
                with self.db.begin_nested():
                    self.db.add(
                        GuardrailPattern(
                            id=pattern_id,
                            source=_BUILT_IN_SOURCE,
                            label=label,
                            pattern_text=None,
                            enabled=True,
                        )
                    )
                    self.db.flush()
            except IntegrityError:
                pass

    def _existing_built_in_ids(self, candidate_ids) -> set[str]:
        """Which of candidate_ids already have a row, as of right now.

        Split out from ensure_built_ins_seeded as its own method so a test
        can simulate the read side of that method's read-then-insert race
        (a concurrent session's SELECT that ran before another session's
        commit) without needing real thread timing -- see
        test_ensure_built_ins_seeded_survives_a_concurrent_duplicate_insert.
        """
        return {
            row.id
            for row in self.db.query(GuardrailPattern.id)
            .filter(GuardrailPattern.id.in_(candidate_ids))
            .all()
        }

    def upsert_custom(self, *, label: str, pattern_text: str, created_by: str) -> GuardrailPattern:
        """Create a new admin-added custom pattern row.

        pattern_text is a literal phrase, matched by check_input as a
        case-insensitive substring -- never compiled as regex (see the
        GuardrailPattern model docstring for why regex support is out of
        scope). Always creates a new row with a generated id; there is no
        update-by-id path for a custom row's text in this issue's scope
        (only enabled can be toggled after creation, via set_enabled).

        Does not commit; the caller owns the transaction.
        """
        pattern = GuardrailPattern(
            id=str(uuid.uuid4()),
            source=_CUSTOM_SOURCE,
            label=label,
            pattern_text=pattern_text,
            enabled=True,
            created_by=created_by,
        )
        self.db.add(pattern)
        self.db.flush()
        return pattern

    def set_enabled(self, pattern_id: str, enabled: bool) -> GuardrailPattern | None:
        """Toggle a pattern (built-in or custom) on or off.

        Returns None for an unknown id rather than raising, so the API
        layer can turn that into a 404 without a try/except.

        Does not commit; the caller owns the transaction.
        """
        pattern = self.get(pattern_id)
        if pattern is None:
            return None

        pattern.enabled = enabled
        self.db.flush()
        return pattern

    def delete_custom(self, pattern_id: str) -> bool:
        """Delete a custom pattern row. Returns False (refuses) for a
        built_in row or an unknown id -- only a custom row is ever
        deletable, since a built-in pattern's row is what carries its
        on/off state and must always exist for that toggle to mean
        anything.

        Does not commit; the caller owns the transaction.
        """
        pattern = self.get(pattern_id)
        if pattern is None or pattern.source != _CUSTOM_SOURCE:
            return False

        self.db.delete(pattern)
        self.db.flush()
        return True
