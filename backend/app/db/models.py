import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    rating: Mapped[int] = mapped_column(default=1200, server_default="1200")
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(unique=True)
    revoked: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str]
    question: Mapped[str]
    constraints: Mapped[str | None]
    difficulty: Mapped[str]  # 'easy' | 'medium' | 'hard'
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    input_data: Mapped[str]
    expected_output: Mapped[str]
    is_public: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


class Duel(Base):
    __tablename__ = "duels"
    __table_args__ = (
    CheckConstraint("player1_id != player2_id", name="ck_duel_players_distinct"),
    CheckConstraint(
        "status IN ('pending', 'ready', 'active', 'finished', 'abandoned')",
        name="ck_duel_status_valid",
    ),
)
    

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    player1_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    player2_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    # 'pending' | 'ready' | 'active' | 'finished' | 'abandoned'
    player1_ready: Mapped[bool] = mapped_column(default=False, server_default="false")
    player2_ready: Mapped[bool] = mapped_column(default=False, server_default="false")
    winner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    duel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("duels.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    problem_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("problems.id"))
    code: Mapped[str]
    verdict: Mapped[str | None]
    # 'accepted' | 'wrong_answer' | 'tle' | 'mle' | 'runtime_error'
    # | 'compile_error' | 'system_error'
    submitted_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, server_default=func.now()
    )