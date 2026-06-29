"""add_fcm_token_to_users

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28

Adds fcm_token column to users table to support Firebase Cloud Messaging push notifications.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("fcm_token", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "fcm_token")
