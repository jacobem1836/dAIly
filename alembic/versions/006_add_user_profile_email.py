"""add email column to user_profile table

Revision ID: 006
Revises: 005
Create Date: 2026-04-17

Adds:
  - user_profile.email: nullable String(255) column for storing the user's
    email address. Used by the scheduler to populate user_email for the ranker
    so WEIGHT_DIRECT fires correctly (FIX-01).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable email column to user_profile."""
    op.add_column(
        "user_profile",
        sa.Column("email", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Remove email column from user_profile."""
    op.drop_column("user_profile", "email")
