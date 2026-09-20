"""Cache AI code reviews on the submission row

Revision ID: d4e5f6a7b801
Revises: c1a2d3e4f501
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b801"
down_revision: Union[str, Sequence[str], None] = "c1a2d3e4f501"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("ai_review", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("submissions", "ai_review")
