"""add timezone column to briefing_config

Revision ID: 007_briefing_config_timezone
Revises: 004
Create Date: 2026-05-01

Adds:
  - briefing_config.timezone: IANA timezone string for per-user schedule DST recalculation
    Existing rows default to 'UTC' via server_default (Plan 21-01, SCHED-TZ-01).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_briefing_config_timezone"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add timezone column to briefing_config table."""
    op.add_column(
        "briefing_config",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="UTC",
        ),
    )


def downgrade() -> None:
    """Remove timezone column from briefing_config table."""
    op.drop_column("briefing_config", "timezone")
