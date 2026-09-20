"""Store the reference solution and editorial, for post-duel analysis

Revision ID: f6a7b8c9d003
Revises: e5f6a7b8c902
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d003"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "problems", sa.Column("reference_solution", postgresql.JSONB(), nullable=True)
    )
    op.add_column("problems", sa.Column("editorial", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("problems", "editorial")
    op.drop_column("problems", "reference_solution")
