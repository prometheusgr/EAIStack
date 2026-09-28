"""Add RAG retrieval/chunking config columns on system_settings

Issue #68: puts the retrieval/chunking knobs identified by the RAG/embedding
config audit (docs/CONFIG_AUDIT_2026-09-04.md, Part 1) on the same
DB-override pattern as guardrail/retention/tracing/rate-limit config - NULL
means "no override, use the env default" (see
app.services.rag_config_service.resolve_rag_config).

rag_similarity_threshold is a cosine-distance cutoff (smaller = more
similar; a match is kept when its distance is below this value), not a
similarity score - see the column comment on the model for the full
rationale. rag_min_chunk_size/rag_chunk_size are independent fields, cross-
validated (min < max) at the API layer in app.api.settings, since a NULL
column can't carry a cross-field bound itself.

Resolved per-call, not once at startup - same resolution timing as
guardrail/rate-limit config, since none of these require a process restart
to take effect.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, 009, 010, 012, and 013 were hand-written:
the local dev Postgres instance is shared with Keycloak, so autogenerate's
diff also picks up Keycloak's entire schema as "to be dropped".

Revision ID: 014
Revises: 013
Create Date: 2026-09-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column("rag_similarity_threshold", sa.Float(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rag_max_results", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rag_min_chunk_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rag_chunk_size", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rag_chunk_overlap_ratio", sa.Float(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("rag_max_excerpt_chars", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "rag_max_excerpt_chars")
    op.drop_column("system_settings", "rag_chunk_overlap_ratio")
    op.drop_column("system_settings", "rag_chunk_size")
    op.drop_column("system_settings", "rag_min_chunk_size")
    op.drop_column("system_settings", "rag_max_results")
    op.drop_column("system_settings", "rag_similarity_threshold")
