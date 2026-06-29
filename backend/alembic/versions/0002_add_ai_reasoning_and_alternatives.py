"""add_ai_reasoning_and_alternatives

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

Adds two new columns to the issues table to support chain-of-thought
prompt engineering:

  ai_reasoning   TEXT    — the model's step-by-step reasoning (2-4 sentences)
  ai_alternatives JSONB  — up to 2 alternative categories with confidence scores
                           e.g. {"drainage": 0.05, "other": 0.02}
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
    )
    op.add_column(
        "issues",
        sa.Column(
            "ai_alternatives",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("issues", "ai_alternatives")
    op.drop_column("issues", "ai_reasoning")
