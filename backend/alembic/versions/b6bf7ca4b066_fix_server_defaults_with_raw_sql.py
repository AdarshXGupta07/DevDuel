"""fix server defaults with raw sql

Revision ID: b6bf7ca4b066
Revises: 7637d486c93e
Create Date: 2026-08-30 12:43:31.784940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6bf7ca4b066'
down_revision: Union[str, Sequence[str], None] = '7637d486c93e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE users ALTER COLUMN rating SET DEFAULT 1200")
    op.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE problems ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE test_cases ALTER COLUMN is_public SET DEFAULT false")
    op.execute("ALTER TABLE test_cases ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE duels ALTER COLUMN status SET DEFAULT 'pending'")
    op.execute("ALTER TABLE duels ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE submissions ALTER COLUMN submitted_at SET DEFAULT now()")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE submissions ALTER COLUMN submitted_at DROP DEFAULT")
    op.execute("ALTER TABLE duels ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE duels ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE test_cases ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE test_cases ALTER COLUMN is_public DROP DEFAULT")
    op.execute("ALTER TABLE problems ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN rating DROP DEFAULT")
