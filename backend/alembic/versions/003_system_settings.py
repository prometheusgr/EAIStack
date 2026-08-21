"""Add system_settings table

Adds the singleton runtime-settings row that lets an admin override
LLM/embedding provider config from the settings UI without restarting the
backend container (see app.db.models.SystemSettings and
app.services.system_settings_service for the fallback-to-env-var logic).

Generated with `alembic revision --autogenerate`, then hand-trimmed: the
local dev Postgres instance is shared with Keycloak, so autogenerate's diff
also picked up Keycloak's entire schema as "to be dropped" (Keycloak's
tables aren't in this app's SQLAlchemy metadata) and a spurious
server_default change on embeddings.embedding. Neither belongs in this
migration, so only the system_settings table creation is kept, matching
migration 001's structure.

Revision ID: 003
Revises: 002
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_url", sa.String(500), nullable=True),
        sa.Column("llm_model", sa.String(255), nullable=True),
        sa.Column("embedding_provider", sa.String(50), nullable=True),
        sa.Column("embedding_url", sa.String(500), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
