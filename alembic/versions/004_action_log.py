"""add action_log table

Revision ID: 004
Revises: 003
Create Date: 2026-04-11

Adds:
  - action_log: append-only audit log for all actions (Plan 04-01, ACT-05)
    Stores body_hash (SHA-256) and content_summary[:200] only — no raw body (T-04-03/SEC-04).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create action_log table."""
    op.create_table(
        "action_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("content_summary", sa.Text(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("approval_status", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop action_log table."""
    op.drop_table("action_log")
