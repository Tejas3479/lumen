"""add_triage_reports_table

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-28

Adds triage_reports table and indexes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "triage_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("issue_id", sa.UUID(), nullable=False),
        sa.Column("reasoning_steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommended_department", sa.String(length=128), nullable=True),
        sa.Column("recommended_priority", sa.Integer(), nullable=False),
        sa.Column("recommended_action", sa.String(length=64), nullable=False),
        sa.Column("recommendation_summary", sa.Text(), nullable=False),
        sa.Column("auto_applied", sa.Boolean(), nullable=False),
        sa.Column("auto_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agent_model", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id"),
    )
    op.create_index(
        "ix_triage_reports_issue_id",
        "triage_reports",
        ["issue_id"],
        unique=True,
    )
    op.create_index(
        "ix_triage_reports_recommended_priority",
        "triage_reports",
        ["recommended_priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_triage_reports_recommended_priority", table_name="triage_reports")
    op.drop_index("ix_triage_reports_issue_id", table_name="triage_reports")
    op.drop_table("triage_reports")
