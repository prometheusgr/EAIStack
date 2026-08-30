"""Add generated tsvector column + GIN index on embeddings.chunk_text

Supports issue #7 Prompt 3 (hybrid search): pure vector similarity is weak
on the highly technical, low-frequency tokens this knowledge base holds
(error codes, version strings, CLI flags) - embeddings smear a rare token
toward semantic neighbors rather than matching it exactly. Postgres
full-text search (tsvector/ts_rank), fused with the existing pgvector
similarity via Reciprocal Rank Fusion, covers exactly that weakness (see
app/repositories/embedding_repository.py's search_hybrid).

chunk_text_search is GENERATED ALWAYS ... STORED: Postgres maintains it on
every insert/update to chunk_text, so no application code needs to keep it
in sync, and querying it never recomputes to_tsvector() per row per query -
a generated/maintained column is preferred over that, per Prompt 3's own
requirement. SQLAlchemy's Column/mapped_column has no portable way to
declare "generated column", so this migration uses op.execute() with raw
DDL rather than op.add_column() (same reasoning migration 002 needed raw
SQL for a pgvector column type change - see docs/DATABASE_MODELS.md's
migration troubleshooting section).

'english' is hardcoded as to_tsvector's text search configuration. Content
here is technical documentation in English; a multi-language corpus would
need a per-row configuration column instead, which is out of scope for this
change.

Written by hand rather than with `alembic revision --autogenerate` (which
cannot express a generated column at all, on top of the usual reason
migrations 003/005/006/007 were hand-written: the shared dev Postgres
picking up Keycloak's schema in the diff).

Revision ID: 008
Revises: 007
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE embeddings "
        "ADD COLUMN chunk_text_search tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', chunk_text)) STORED"
    )
    op.create_index(
        "ix_embeddings_chunk_text_search",
        "embeddings",
        ["chunk_text_search"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_embeddings_chunk_text_search", table_name="embeddings")
    op.drop_column("embeddings", "chunk_text_search")
