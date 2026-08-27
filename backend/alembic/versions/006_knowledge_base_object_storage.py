"""Add object-storage columns to knowledge_base

Phase 5 follow-up (issue #13): file uploads are stored in MinIO, with
extracted text kept in `content` as before (search and embedding continue
to operate on it unchanged). These three columns record where the
original file lives and what it was, and are NULL for the pre-existing
paste-text flow - NULL, not empty string, distinguishes "no file" from
"file with no name".

storage_key is a MinIO object path scoped as
f"{user_id}/{kb_id}/{filename}" (see app.storage.object_keys) - it is
never a bare client-supplied key, so per-user object isolation holds
structurally rather than by convention.

Written by hand rather than with `alembic revision --autogenerate`, for
the same reason migrations 003 and 005 were: the local dev Postgres
instance is shared with Keycloak, so autogenerate's diff also picks up
Keycloak's entire schema as "to be dropped".

Revision ID: 006
Revises: 005
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("knowledge_base", sa.Column("storage_key", sa.String(1024), nullable=True))
    op.add_column("knowledge_base", sa.Column("original_filename", sa.String(500), nullable=True))
    op.add_column("knowledge_base", sa.Column("content_type", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_base", "content_type")
    op.drop_column("knowledge_base", "original_filename")
    op.drop_column("knowledge_base", "storage_key")
