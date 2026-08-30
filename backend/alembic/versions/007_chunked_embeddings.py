"""Add chunk_index/chunk_text/heading_path to embeddings

Supports issue #7 Prompt 2 (structure-aware chunking): a document is now
split into passage-sized chunks before embedding
(see app.services.chunking_service), so multiple Embedding rows typically
share one doc_id instead of one row per document.

Purely additive - no existing row is touched or backfilled. There is no
production data and dev data is disposable, so a backfill of pre-chunking
rows was deliberately scoped out (see docs/RETRIEVAL_IMPROVEMENT_PROMPTS.md's
Prompt 2 and the follow-up issue for an admin-triggered reindex capability).
A pre-existing row keeps its one-vector-per-document shape
(chunk_index=0, chunk_text="", heading_path=NULL) and continues to work
with the existing (non-chunk-aware) retrieval path until the document it
belongs to is next created/updated, which chunks it via the normal write
path.

chunk_text defaults to "" rather than being nullable: every row, old or
new, must have *some* text for retrieval to return, and an empty string is
a clearer signal of "not yet chunked" than NULL would be for a NOT NULL-
shaped column. heading_path is nullable since "no enclosing heading" is a
real, common case (see chunking_service.Chunk), not a migration artifact.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migrations 003, 005, and 006 were: the local dev Postgres
instance is shared with Keycloak, so autogenerate's diff also picks up
Keycloak's entire schema as "to be dropped".

Revision ID: 007
Revises: 006
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "embeddings",
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "embeddings",
        sa.Column("chunk_text", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "embeddings",
        sa.Column("heading_path", sa.String(1000), nullable=True),
    )
    op.create_index(
        "ix_embeddings_doc_id_chunk_index",
        "embeddings",
        ["doc_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_embeddings_doc_id_chunk_index", table_name="embeddings")
    op.drop_column("embeddings", "heading_path")
    op.drop_column("embeddings", "chunk_text")
    op.drop_column("embeddings", "chunk_index")
