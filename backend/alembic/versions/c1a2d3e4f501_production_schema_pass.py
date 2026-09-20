"""Production schema pass: plans, ranked mode, cap counter, rating history, anti-cheat log

Covers §4 of docs/production-plan.md plus the timestamptz half of the §3 P0 list.

Revision ID: c1a2d3e4f501
Revises: 11340bdf1dd7
Create Date: 2026-09-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1a2d3e4f501"
down_revision: Union[str, Sequence[str], None] = "11340bdf1dd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)

# Every naive `timestamp` column that must become `timestamptz`. The existing values were
# written by `datetime.utcnow()`, so they are UTC wall-clock — `AT TIME ZONE 'UTC'` is the
# correct reinterpretation, not a shift.
NAIVE_TIMESTAMP_COLUMNS = [
    ("users", "created_at"),
    ("refresh_tokens", "created_at"),
    ("problems", "created_at"),
    ("test_cases", "created_at"),
    ("duels", "created_at"),
    ("duels", "started_at"),
    ("duels", "finished_at"),
    ("submissions", "submitted_at"),
]


def upgrade() -> None:
    # ------------------------------------------------------------------ timestamptz
    for table, column in NAIVE_TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=TS,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )

    # ------------------------------------------------------------------ users
    op.add_column("users", sa.Column("plan", sa.String(), nullable=False, server_default="free"))
    op.add_column("users", sa.Column("plan_expires_at", TS, nullable=True))
    op.add_column(
        "users",
        sa.Column("ranked_matches_played", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column("users", sa.Column("banned_reason", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_seen_at", TS, nullable=True))
    op.add_column("users", sa.Column("deleted_at", TS, nullable=True))
    op.create_check_constraint("ck_user_plan_valid", "users", "plan IN ('free', 'paid')")
    op.create_index("ix_users_rating", "users", ["rating"])

    # ------------------------------------------------------------------ refresh_tokens
    # Existing rows hold *raw* tokens that cannot be recovered once hashed, and they are
    # all test-session tokens. Clearing them logs everyone out, which is the correct and
    # cheap answer at this stage.
    op.execute("DELETE FROM refresh_tokens")
    op.drop_column("refresh_tokens", "token")
    op.add_column("refresh_tokens", sa.Column("token_hash", sa.String(), nullable=False))
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("refresh_tokens", sa.Column("expires_at", TS, nullable=False))
    op.create_unique_constraint("uq_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_foreign_key(
        "fk_refresh_tokens_replaced_by",
        "refresh_tokens",
        "refresh_tokens",
        ["replaced_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    # ------------------------------------------------------------------ problems
    op.add_column("problems", sa.Column("slug", sa.String(), nullable=True))
    op.execute(
        "UPDATE problems SET slug = 'legacy-' || left(id::text, 8) WHERE slug IS NULL"
    )
    op.alter_column("problems", "slug", nullable=False)
    op.create_unique_constraint("uq_problems_slug", "problems", ["slug"])
    op.add_column("problems", sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column(
        "problems",
        sa.Column("time_limit_ms", sa.Integer(), nullable=False, server_default="5000"),
    )
    op.add_column(
        "problems",
        sa.Column("memory_limit_mb", sa.Integer(), nullable=False, server_default="256"),
    )
    op.add_column("problems", sa.Column("starter_code", postgresql.JSONB(), nullable=True))
    op.add_column(
        "problems", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true")
    )
    op.add_column("problems", sa.Column("source", sa.String(), nullable=True))
    op.add_column("problems", sa.Column("license", sa.String(), nullable=True))
    op.alter_column("problems", "question", type_=sa.Text())
    op.alter_column("problems", "constraints", type_=sa.Text())
    op.create_check_constraint(
        "ck_problem_difficulty", "problems", "difficulty IN ('easy', 'medium', 'hard')"
    )
    op.create_index("ix_problems_active_difficulty", "problems", ["is_active", "difficulty"])

    # ------------------------------------------------------------------ test_cases
    op.add_column(
        "test_cases", sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("test_cases", sa.Column("weight", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("test_cases", "input_data", type_=sa.Text())
    op.alter_column("test_cases", "expected_output", type_=sa.Text())
    op.create_index("ix_test_cases_problem_ordinal", "test_cases", ["problem_id", "ordinal"])

    # ------------------------------------------------------------------ duels
    op.add_column("duels", sa.Column("mode", sa.String(), nullable=False, server_default="casual"))
    op.add_column(
        "duels", sa.Column("language", sa.String(), nullable=False, server_default="python")
    )
    op.add_column(
        "duels",
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False, server_default="900"),
    )
    op.add_column("duels", sa.Column("starts_at", TS, nullable=True))
    op.add_column("duels", sa.Column("ends_at", TS, nullable=True))
    op.add_column("duels", sa.Column("end_reason", sa.String(), nullable=True))
    op.add_column("duels", sa.Column("p1_rating_before", sa.Integer(), nullable=True))
    op.add_column("duels", sa.Column("p1_rating_after", sa.Integer(), nullable=True))
    op.add_column("duels", sa.Column("p2_rating_before", sa.Integer(), nullable=True))
    op.add_column("duels", sa.Column("p2_rating_after", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_duel_mode_valid", "duels", "mode IN ('casual', 'ranked')")
    op.create_index("ix_duels_player1_status", "duels", ["player1_id", "status"])
    op.create_index("ix_duels_player2_status", "duels", ["player2_id", "status"])
    op.create_index("ix_duels_ends_at", "duels", ["ends_at"])

    # ------------------------------------------------------------------ submissions
    op.add_column(
        "submissions", sa.Column("language", sa.String(), nullable=False, server_default="python")
    )
    op.add_column(
        "submissions", sa.Column("tests_passed", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "submissions", sa.Column("tests_total", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("submissions", sa.Column("runtime_ms", sa.Integer(), nullable=True))
    op.add_column("submissions", sa.Column("memory_kb", sa.Integer(), nullable=True))
    op.add_column(
        "submissions", sa.Column("is_final", sa.Boolean(), nullable=False, server_default="true")
    )
    op.add_column("submissions", sa.Column("stderr_excerpt", sa.Text(), nullable=True))
    op.alter_column("submissions", "code", type_=sa.Text())
    op.alter_column("submissions", "duel_id", nullable=True)
    op.create_index("ix_submissions_duel_id", "submissions", ["duel_id"])
    op.create_index("ix_submissions_user_id", "submissions", ["user_id"])

    # ------------------------------------------------------------------ new tables
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="razorpay"),
        sa.Column("provider_sub_id", sa.String(), nullable=False, unique=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_period_end", TS, nullable=True),
        sa.Column("amount_paise", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="razorpay"),
        sa.Column("provider_event_id", sa.String(), nullable=False, unique=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "ranked_daily_usage",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("usage_date", sa.Date(), primary_key=True),
        sa.Column("matches_started", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "rating_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "duel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("duels.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating_before", sa.Integer(), nullable=False),
        sa.Column("rating_after", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("k_factor", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rating_history_user_created", "rating_history", ["user_id", "created_at"])

    op.create_table(
        "match_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "duel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("duels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("client_ts", TS, nullable=True),
        sa.Column("server_ts", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("duel_id", "user_id", "seq", name="uq_match_event_seq"),
    )
    op.create_index("ix_match_events_duel", "match_events", ["duel_id"])
    op.create_index("ix_match_events_server_ts", "match_events", ["server_ts"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reported_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "duel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("duels.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reports_status", "reports", ["status"])

    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("rooms")
    op.drop_table("reports")
    op.drop_table("match_events")
    op.drop_table("rating_history")
    op.drop_table("ranked_daily_usage")
    op.drop_table("payments")
    op.drop_table("subscriptions")

    op.drop_index("ix_submissions_user_id", table_name="submissions")
    op.drop_index("ix_submissions_duel_id", table_name="submissions")
    for column in (
        "stderr_excerpt",
        "is_final",
        "memory_kb",
        "runtime_ms",
        "tests_total",
        "tests_passed",
        "language",
    ):
        op.drop_column("submissions", column)

    op.drop_index("ix_duels_ends_at", table_name="duels")
    op.drop_index("ix_duels_player2_status", table_name="duels")
    op.drop_index("ix_duels_player1_status", table_name="duels")
    op.drop_constraint("ck_duel_mode_valid", "duels", type_="check")
    for column in (
        "p2_rating_after",
        "p2_rating_before",
        "p1_rating_after",
        "p1_rating_before",
        "end_reason",
        "ends_at",
        "starts_at",
        "time_limit_seconds",
        "language",
        "mode",
    ):
        op.drop_column("duels", column)

    op.drop_index("ix_test_cases_problem_ordinal", table_name="test_cases")
    op.drop_column("test_cases", "weight")
    op.drop_column("test_cases", "ordinal")

    op.drop_index("ix_problems_active_difficulty", table_name="problems")
    op.drop_constraint("ck_problem_difficulty", "problems", type_="check")
    for column in (
        "license",
        "source",
        "is_active",
        "starter_code",
        "memory_limit_mb",
        "time_limit_ms",
        "tags",
    ):
        op.drop_column("problems", column)
    op.drop_constraint("uq_problems_slug", "problems", type_="unique")
    op.drop_column("problems", "slug")

    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_constraint("fk_refresh_tokens_replaced_by", "refresh_tokens", type_="foreignkey")
    op.drop_constraint("uq_refresh_tokens_token_hash", "refresh_tokens", type_="unique")
    op.execute("DELETE FROM refresh_tokens")
    op.drop_column("refresh_tokens", "expires_at")
    op.drop_column("refresh_tokens", "replaced_by_id")
    op.drop_column("refresh_tokens", "family_id")
    op.drop_column("refresh_tokens", "token_hash")
    op.add_column("refresh_tokens", sa.Column("token", sa.String(), nullable=False))

    op.drop_index("ix_users_rating", table_name="users")
    op.drop_constraint("ck_user_plan_valid", "users", type_="check")
    for column in (
        "deleted_at",
        "last_seen_at",
        "banned_reason",
        "is_banned",
        "ranked_matches_played",
        "plan_expires_at",
        "plan",
    ):
        op.drop_column("users", column)

    for table, column in NAIVE_TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
