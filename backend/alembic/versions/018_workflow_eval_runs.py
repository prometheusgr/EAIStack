"""Workflow eval runs and their per-case results

Issue #84 slice B (epic #80): an admin runs a workflow version's test suite
(declared in its YAML) and sees a pass rate per case. workflow_eval_runs is
the job record; workflow_eval_case_results holds one scored row per run of
each case. Neither holds conversation content. Also adds the
eval_case_run_timeout_seconds admin override to system_settings.

Written by hand rather than with `alembic revision --autogenerate`, for the
same reason as migrations 003-017: the local dev Postgres instance is shared
with Keycloak, so autogenerate's diff also picks up Keycloak's schema.

Revision ID: 018
Revises: 017
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_eval_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("workflow_version_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("case_runs_total", sa.Integer(), nullable=False),
        sa.Column("case_runs_done", sa.Integer(), nullable=False),
        sa.Column("active_slot", sa.Boolean(), nullable=True),
        sa.Column("started_by_user_id", sa.String(255), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workflow_version_id"], ["workflow_versions.id"]),
        sa.UniqueConstraint("active_slot", name="uq_workflow_eval_runs_active_slot"),
    )
    op.create_index("ix_workflow_eval_runs_workflow_name", "workflow_eval_runs", ["workflow_name"])
    op.create_index(
        "ix_workflow_eval_runs_workflow_version_id", "workflow_eval_runs", ["workflow_version_id"]
    )

    op.create_table(
        "workflow_eval_case_results",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("eval_run_id", sa.String(36), nullable=False),
        sa.Column("case_name", sa.String(255), nullable=False),
        sa.Column("run_index", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["eval_run_id"], ["workflow_eval_runs.id"]),
        sa.UniqueConstraint(
            "eval_run_id", "case_name", "run_index", name="uq_workflow_eval_case_results_run"
        ),
    )
    op.create_index(
        "ix_workflow_eval_case_results_eval_run_id", "workflow_eval_case_results", ["eval_run_id"]
    )

    op.add_column(
        "system_settings",
        sa.Column("eval_case_run_timeout_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "eval_case_run_timeout_seconds")
    op.drop_index(
        "ix_workflow_eval_case_results_eval_run_id", table_name="workflow_eval_case_results"
    )
    op.drop_table("workflow_eval_case_results")
    op.drop_index("ix_workflow_eval_runs_workflow_version_id", table_name="workflow_eval_runs")
    op.drop_index("ix_workflow_eval_runs_workflow_name", table_name="workflow_eval_runs")
    op.drop_table("workflow_eval_runs")
