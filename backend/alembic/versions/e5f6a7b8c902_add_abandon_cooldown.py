"""Rage-quit deterrent: per-day abandon count and a matchmaking cooldown

Revision ID: e5f6a7b8c902
Revises: d4e5f6a7b801
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c902"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("abandons_today", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("users", sa.Column("abandons_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("matchmaking_blocked_until", TS, nullable=True))
    # Queried on every matchmaking attempt by a blocked user only, but cheap to have.
    op.create_index(
        "ix_users_matchmaking_blocked_until", "users", ["matchmaking_blocked_until"]
    )


def downgrade() -> None:
    op.drop_index("ix_users_matchmaking_blocked_until", table_name="users")
    op.drop_column("users", "matchmaking_blocked_until")
    op.drop_column("users", "abandons_date")
    op.drop_column("users", "abandons_today")
