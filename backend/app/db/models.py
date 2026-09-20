import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    Everything in this schema is `timestamptz`. `datetime.utcnow()` returns a *naive*
    datetime, which Postgres then interprets in the session timezone — the classic way
    to get timers, daily-cap resets and rating history quietly wrong by 5h30m.
    """
    return datetime.now(timezone.utc)


# A `timestamptz` column type, used everywhere below.
TS = DateTime(timezone=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    rating: Mapped[int] = mapped_column(default=1200, server_default="1200")

    # --- subscription / plan gating ---
    plan: Mapped[str] = mapped_column(default="free", server_default="free")  # 'free' | 'paid'
    plan_expires_at: Mapped[datetime | None] = mapped_column(TS)

    # --- rating calibration: K=40 for the first 20 ranked matches, then K=20 ---
    ranked_matches_played: Mapped[int] = mapped_column(default=0, server_default="0")

    # --- moderation ---
    is_banned: Mapped[bool] = mapped_column(default=False, server_default="false")
    banned_reason: Mapped[str | None] = mapped_column(Text)

    # --- rage-quit deterrent (ADR-0042) ---
    # Counted per day so a bad afternoon does not follow someone around forever.
    abandons_today: Mapped[int] = mapped_column(default=0, server_default="0")
    abandons_date: Mapped[date | None] = mapped_column(Date)
    matchmaking_blocked_until: Mapped[datetime | None] = mapped_column(TS)

    last_seen_at: Mapped[datetime | None] = mapped_column(TS)
    # Account deletion anonymises rather than DELETEs: duels and submissions reference
    # users and are also the *opponent's* history, which is not the deleter's to erase.
    deleted_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        CheckConstraint("plan IN ('free', 'paid')", name="ck_user_plan_valid"),
        Index("ix_users_rating", "rating"),
    )

    @property
    def is_paid(self) -> bool:
        """Paid *right now* — a plan flag with a lapsed expiry is not a paid plan."""
        if self.plan != "paid":
            return False
        if self.plan_expires_at is None:
            return True
        return self.plan_expires_at > utcnow()


class RefreshToken(Base):
    """One row per issued refresh token.

    Tokens are stored **hashed** — a leaked database dump must not hand the attacker
    working sessions. `family_id` groups a rotation chain so that reuse of any already-
    rotated token can revoke the whole family at once (reuse detection, ADR-0023).
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    revoked: Mapped[bool] = mapped_column(default=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(default="razorpay", server_default="razorpay")
    provider_sub_id: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str]
    # 'created'|'authenticated'|'active'|'pending'|'halted'|'cancelled'|'completed'|'expired'
    current_period_end: Mapped[datetime | None] = mapped_column(TS)
    amount_paise: Mapped[int] = mapped_column(default=5000, server_default="5000")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_subscriptions_user_id", "user_id"),)


class Payment(Base):
    """Append-only ledger of processed provider events.

    `provider_event_id` is UNIQUE and that is the entire idempotency mechanism: payment
    webhooks are at-least-once, so the same event *will* arrive twice (Day 10's delivery
    semantics, now with money attached).
    """

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(default="razorpay", server_default="razorpay")
    provider_event_id: Mapped[str] = mapped_column(unique=True)
    event_type: Mapped[str]
    amount_paise: Mapped[int | None]
    status: Mapped[str | None]
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(unique=True)
    title: Mapped[str]
    question: Mapped[str] = mapped_column(Text)
    constraints: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[str]  # 'easy' | 'medium' | 'hard'
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    # Per-problem judge limits; fall back to the global defaults when NULL.
    time_limit_ms: Mapped[int] = mapped_column(default=5000, server_default="5000")
    memory_limit_mb: Mapped[int] = mapped_column(default=256, server_default="256")

    # {"python": "def solve(...):\n    ...", "javascript": "function solve(...) {}"}
    starter_code: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")

    # {"python": "...", "cpp": "..."} — shown ONLY after a duel is finished. This is the
    # answer key; leaking it mid-duel would end the product.
    reference_solution: Mapped[dict | None] = mapped_column(JSONB)
    # Optional prose: why the reference approach is the right one.
    editorial: Mapped[str | None] = mapped_column(Text)

    # Provenance matters: every problem must be original or licensed. See docs/problems.md.
    source: Mapped[str | None]
    license: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_problem_difficulty"),
        Index("ix_problems_active_difficulty", "is_active", "difficulty"),
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(default=0, server_default="0")
    input_data: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    weight: Mapped[int] = mapped_column(default=1, server_default="1")
    # Public/sample cases are shown to the player and runnable via "Run".
    is_public: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_test_cases_problem_ordinal", "problem_id", "ordinal"),)


class Duel(Base):
    __tablename__ = "duels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    player1_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    player2_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))

    # 'casual' | 'ranked' — decided at queue time, never changes. Drives matchmaking,
    # ELO, anti-cheat strictness and daily-cap accounting.
    mode: Mapped[str] = mapped_column(default="casual", server_default="casual")
    language: Mapped[str] = mapped_column(default="python", server_default="python")

    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    # 'pending' | 'ready' | 'active' | 'finished' | 'abandoned'

    player1_ready: Mapped[bool] = mapped_column(default=False, server_default="false")
    player2_ready: Mapped[bool] = mapped_column(default=False, server_default="false")

    time_limit_seconds: Mapped[int] = mapped_column(default=900, server_default="900")
    # Server-authoritative clock. Clients count down to these; they are never sent ticks.
    starts_at: Mapped[datetime | None] = mapped_column(TS)
    ends_at: Mapped[datetime | None] = mapped_column(TS)

    winner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    end_reason: Mapped[str | None]
    # 'solved' | 'timeout' | 'forfeit' | 'disconnect' | 'abandoned' | 'draw'

    # Rating snapshot, so history is readable without replaying every match.
    p1_rating_before: Mapped[int | None]
    p1_rating_after: Mapped[int | None]
    p2_rating_before: Mapped[int | None]
    p2_rating_after: Mapped[int | None]

    started_at: Mapped[datetime | None] = mapped_column(TS)
    finished_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        CheckConstraint("player1_id != player2_id", name="ck_duel_players_distinct"),
        CheckConstraint(
            "status IN ('pending', 'ready', 'active', 'finished', 'abandoned')",
            name="ck_duel_status_valid",
        ),
        CheckConstraint("mode IN ('casual', 'ranked')", name="ck_duel_mode_valid"),
        # The two indexes behind "which active duel is this user in?" — the lookup Day 10's
        # disconnect handler does on every single dropped connection.
        Index("ix_duels_player1_status", "player1_id", "status"),
        Index("ix_duels_player2_status", "player2_id", "status"),
        Index("ix_duels_ends_at", "ends_at"),
    )

    def opponent_of(self, user_id) -> uuid.UUID | None:
        if str(self.player1_id) == str(user_id):
            return self.player2_id
        if str(self.player2_id) == str(user_id):
            return self.player1_id
        return None

    def has_player(self, user_id) -> bool:
        return str(user_id) in (str(self.player1_id), str(self.player2_id))


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    duel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("duels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    language: Mapped[str] = mapped_column(default="python", server_default="python")
    code: Mapped[str] = mapped_column(Text)

    verdict: Mapped[str | None]
    # 'accepted' | 'wrong_answer' | 'tle' | 'mle' | 'runtime_error'
    # | 'compile_error' | 'system_error'
    tests_passed: Mapped[int] = mapped_column(default=0, server_default="0")
    tests_total: Mapped[int] = mapped_column(default=0, server_default="0")
    runtime_ms: Mapped[int | None]
    memory_kb: Mapped[int | None]
    # A "Run samples" click is not a submission attempt; only is_final counts for winning.
    is_final: Mapped[bool] = mapped_column(default=True, server_default="true")
    stderr_excerpt: Mapped[str | None] = mapped_column(Text)
    # Cached AI review. Stored because a player reopens a result screen repeatedly and
    # regenerating would pay for the same answer twice.
    ai_review: Mapped[dict | None] = mapped_column(JSONB)

    submitted_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        Index("ix_submissions_duel_id", "duel_id"),
        Index("ix_submissions_user_id", "user_id"),
    )


class RankedDailyUsage(Base):
    """The free-tier ranked cap, as a counter table rather than a COUNT(*) over duels.

    Claiming a slot is one atomic statement (see `matchmaking_service.claim_ranked_slot`),
    which is the same Day 9 trick: the database decides the winner, not Python.
    `usage_date` is the date in `settings.daily_reset_timezone`, i.e. a fixed IST midnight
    reset rather than a rolling 24h window (ADR-0024).
    """

    __tablename__ = "ranked_daily_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    usage_date: Mapped[date] = mapped_column(Date, primary_key=True)
    matches_started: Mapped[int] = mapped_column(default=0, server_default="0")
    matches_completed: Mapped[int] = mapped_column(default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())


class RatingHistory(Base):
    __tablename__ = "rating_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    duel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("duels.id", ondelete="SET NULL"))
    rating_before: Mapped[int]
    rating_after: Mapped[int]
    delta: Mapped[int]
    k_factor: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_rating_history_user_created", "user_id", "created_at"),)


class MatchEvent(Base):
    """Behavioural log for anti-cheat (keystroke rhythm, large inserts, focus changes).

    This is the highest-volume table in the system by an order of magnitude — clients
    batch and flush every ~2s, and rows are archived out after the retention window
    (ADR-0025: 30 days hot, then cold storage). Never query it on a request path.
    """

    __tablename__ = "match_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    duel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duels.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str]
    # 'keystroke_batch' | 'paste_attempt' | 'large_insert' | 'focus' | 'blur' | 'run' | 'submit'
    payload: Mapped[dict | None] = mapped_column(JSONB)
    client_ts: Mapped[datetime | None] = mapped_column(TS)
    server_ts: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("duel_id", "user_id", "seq", name="uq_match_event_seq"),
        Index("ix_match_events_duel", "duel_id"),
        Index("ix_match_events_server_ts", "server_ts"),
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reported_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    duel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("duels.id", ondelete="SET NULL"))
    reason: Mapped[str]
    detail: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="open", server_default="open")
    # 'open' | 'reviewing' | 'actioned' | 'dismissed'
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_reports_status", "status"),)


class Room(Base):
    """Private rooms (Phase 3). Table exists now so the FK shape is settled early."""

    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(unique=True)
    host_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_private: Mapped[bool] = mapped_column(default=True, server_default="true")
    settings: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, server_default=func.now())
