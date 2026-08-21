"""Add audit_logs table and retention columns on system_settings

Adds Phase 4b's data-retention configuration and the first audit record in
the system.

The four new system_settings columns are nullable for the same reason the
existing provider columns are: NULL means "no override, use the env
default" (see app.services.retention_service.resolve_retention_config).
This matters more here than for the provider fields, because 0 is a
legitimate retention override meaning "purge immediately" and False is a
legitimate cleanup_on_logout override - neither can be encoded as "unset",
so the resolver tests `is not None` rather than truthiness.

audit_logs is append-only by design: no application code updates or
deletes a row, AuditLogRepository deliberately exposes no delete method,
and no retention purge path queries this table. That is the enforcement of
docs/SECURITY.md's guarantee that audit records survive every purge and are
retained on a schedule independent of session/conversation data.

old_value/new_value are strings rather than typed columns so one table can
record changes to settings of any type (int hours, bool flags) without a
column per setting.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason migration 003 was hand-trimmed: the local dev Postgres instance
is shared with Keycloak, so autogenerate's diff also picks up Keycloak's
entire schema as "to be dropped".

Revision ID: 005
Revises: 004
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("old_value", sa.String(500), nullable=True),
        sa.Column("new_value", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.add_column(
        "system_settings",
        sa.Column("conversation_retention_hours", sa.Integer(), nullable=True),
    )
    op.add_column("system_settings", sa.Column("cleanup_on_logout", sa.Boolean(), nullable=True))
    op.add_column(
        "system_settings",
        sa.Column("knowledge_base_purge_days", sa.Integer(), nullable=True),
    )
    op.add_column(
        "system_settings",
        sa.Column("api_key_purge_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "api_key_purge_days")
    op.drop_column("system_settings", "knowledge_base_purge_days")
    op.drop_column("system_settings", "cleanup_on_logout")
    op.drop_column("system_settings", "conversation_retention_hours")

    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
