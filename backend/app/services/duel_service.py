import uuid
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Duel, Submission, utcnow

TRANSITIONS = {
    "pending": ["ready", "abandoned"],
    "ready": ["active", "abandoned"],
    "active": ["finished", "abandoned"],
    "finished": [],
    "abandoned": [],
}

ACTIVE_STATUSES = ("pending", "ready", "active")


class DuelNotFound(Exception):
    pass


class IllegalTransition(Exception):
    pass


class NotAParticipant(Exception):
    pass


def as_uuid(value) -> uuid.UUID:
    """Every id crossing a boundary becomes a real UUID here, or raises.

    Postgres will happily coerce a string, but a malformed one produces a driver-level
    error deep in a query instead of a clean rejection at the edge.
    """
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise DuelNotFound(f"Not a valid id: {value!r}")


def legal_transition(current_status: str, new_status: str) -> None:
    if new_status not in TRANSITIONS.get(current_status, []):
        raise IllegalTransition(
            f"Illegal status transition from {current_status} to {new_status}"
        )


async def get_duel(db: AsyncSession, duel_id) -> Duel:
    result = await db.execute(select(Duel).where(Duel.id == as_uuid(duel_id)))
    duel = result.scalar_one_or_none()
    if duel is None:
        raise DuelNotFound(f"Duel {duel_id} not found.")
    return duel


async def create_duel(
    db: AsyncSession,
    player1_id,
    player2_id,
    problem_id,
    duel_id=None,
    mode: str = "casual",
    language: str = "python",
    time_limit_seconds: int | None = None,
) -> Duel:
    duel = Duel(
        id=as_uuid(duel_id) if duel_id else uuid.uuid4(),
        player1_id=as_uuid(player1_id),
        player2_id=as_uuid(player2_id),
        problem_id=as_uuid(problem_id),
        mode=mode,
        language=language,
        time_limit_seconds=time_limit_seconds or settings.duel_time_limit_seconds,
        status="pending",
    )
    db.add(duel)
    await db.commit()
    await db.refresh(duel)
    return duel


async def transition_duel(db: AsyncSession, duel_id, new_status: str) -> Duel:
    duel = await get_duel(db, duel_id)
    legal_transition(duel.status, new_status)
    duel.status = new_status
    await db.commit()
    await db.refresh(duel)
    return duel


async def find_active_duel_for_user(db: AsyncSession, user_id) -> Duel | None:
    """The lookup Day 10's disconnect handler runs on every dropped connection.

    Backed by ix_duels_player1_status / ix_duels_player2_status — without those this is
    a sequential scan of every duel ever played, on every disconnect.
    """
    user_uuid = as_uuid(user_id)
    result = await db.execute(
        select(Duel)
        .where(
            or_(Duel.player1_id == user_uuid, Duel.player2_id == user_uuid),
            Duel.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Duel.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def mark_ready(db: AsyncSession, duel_id, user_id) -> dict:
    """Ready-up, race-safe. Day 9's logic, now also setting the match clock."""
    duel = await get_duel(db, duel_id)

    if str(duel.player1_id) == str(user_id):
        ready_field = "player1_ready"
    elif str(duel.player2_id) == str(user_id):
        ready_field = "player2_ready"
    else:
        raise NotAParticipant(f"User {user_id} is not a participant in duel {duel_id}.")

    # Step 1: each player only ever writes their own column, so this cannot collide.
    await db.execute(
        update(Duel).where(Duel.id == duel.id).values(**{ready_field: True})
    )
    await db.commit()

    # Step 2: one atomic check-and-act. Two simultaneous ready events can both reach
    # here, but only one can match `status == 'ready'` — the loser's WHERE finds nothing.
    starts_at = utcnow() + timedelta(seconds=settings.countdown_seconds)
    ends_at = starts_at + timedelta(seconds=duel.time_limit_seconds)

    result = await db.execute(
        update(Duel)
        .where(
            Duel.id == duel.id,
            Duel.status == "ready",
            Duel.player1_ready.is_(True),
            Duel.player2_ready.is_(True),
        )
        .values(
            status="active",
            started_at=utcnow(),
            starts_at=starts_at,
            ends_at=ends_at,
        )
    )
    await db.commit()

    started = result.rowcount == 1
    return {
        "started": started,
        "duel_id": str(duel.id),
        "starts_at": starts_at.isoformat() if started else None,
        "ends_at": ends_at.isoformat() if started else None,
    }


async def finish_duel(db: AsyncSession, duel_id, winner_id, end_reason: str) -> Duel | None:
    """Resolve an active duel exactly once.

    The same atomic-update trick as ready-up: `WHERE status = 'active'` means the first
    caller wins and every later one (a timeout firing as a submission lands, a grace
    timer racing a forfeit) changes nothing and gets None back.
    """
    duel_uuid = as_uuid(duel_id)
    result = await db.execute(
        update(Duel)
        .where(Duel.id == duel_uuid, Duel.status == "active")
        .values(
            status="finished",
            winner_id=as_uuid(winner_id) if winner_id else None,
            end_reason=end_reason,
            finished_at=utcnow(),
        )
    )
    await db.commit()

    if result.rowcount != 1:
        return None
    return await get_duel(db, duel_uuid)


async def abandon_duel(db: AsyncSession, duel_id, end_reason: str = "abandoned") -> Duel | None:
    """For duels that die before they ever go active (both players gone during ready-up)."""
    result = await db.execute(
        update(Duel)
        .where(Duel.id == as_uuid(duel_id), Duel.status.in_(("pending", "ready")))
        .values(status="abandoned", end_reason=end_reason, finished_at=utcnow())
    )
    await db.commit()
    if result.rowcount != 1:
        return None
    return await get_duel(db, duel_id)


async def best_submission_for(db: AsyncSession, duel_id, user_id) -> Submission | None:
    """Best final submission: most tests passed, then earliest — the §4.1 tiebreak rule."""
    result = await db.execute(
        select(Submission)
        .where(
            Submission.duel_id == as_uuid(duel_id),
            Submission.user_id == as_uuid(user_id),
            Submission.is_final.is_(True),
        )
        .order_by(Submission.tests_passed.desc(), Submission.submitted_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def resolve_on_timeout(db: AsyncSession, duel_id) -> tuple[Duel | None, dict]:
    """Decide a duel where the clock ran out.

    **The rule (ADR-0044, superseding ADR-0026): if neither player actually solved the
    problem, it is a draw — regardless of partial progress.**

    The earlier design awarded the win to whoever passed more hidden tests. That is worse
    than it sounds: passing 4 of 7 tests can mean a genuinely better attempt, or it can
    mean a wrong solution that happens to survive the easy cases. Ranking two failures
    against each other reads signal into noise, and it rewards writing something that
    games the samples over writing something that nearly works.

    Neither solved it → nobody won → nothing to update. Progress is still reported, so
    both players can see where they got to; it just doesn't decide the match.
    """
    duel = await get_duel(db, duel_id)
    p1 = await best_submission_for(db, duel.id, duel.player1_id)
    p2 = await best_submission_for(db, duel.id, duel.player2_id)

    def solved(sub: Submission | None) -> bool:
        return sub is not None and sub.verdict == "accepted"

    # A genuine solve during the last moments still wins — `finish_duel` on the submit
    # path usually gets there first, but this covers the race at the boundary.
    if solved(p1) and not solved(p2):
        winner_id, reason = duel.player1_id, "solved"
    elif solved(p2) and not solved(p1):
        winner_id, reason = duel.player2_id, "solved"
    else:
        winner_id, reason = None, "draw"

    finished = await finish_duel(db, duel.id, winner_id, reason)
    detail = {
        "player1": {
            "tests_passed": p1.tests_passed if p1 else 0,
            "tests_total": p1.tests_total if p1 else 0,
            "solved": solved(p1),
            "submitted": p1 is not None,
        },
        "player2": {
            "tests_passed": p2.tests_passed if p2 else 0,
            "tests_total": p2.tests_total if p2 else 0,
            "solved": solved(p2),
            "submitted": p2 is not None,
        },
        "neither_solved": not solved(p1) and not solved(p2),
    }
    return finished, detail


def serialize_duel(duel: Duel) -> dict:
    """Everything a reconnecting client needs to redraw the screen, and nothing more.

    Note what is absent: any player's code. Opponent code is only ever revealed by the
    post-match endpoint, after the duel is finished.
    """
    return {
        "id": str(duel.id),
        "mode": duel.mode,
        "language": duel.language,
        "status": duel.status,
        "problem_id": str(duel.problem_id),
        "player1_id": str(duel.player1_id),
        "player2_id": str(duel.player2_id),
        "player1_ready": duel.player1_ready,
        "player2_ready": duel.player2_ready,
        "winner_id": str(duel.winner_id) if duel.winner_id else None,
        "end_reason": duel.end_reason,
        "time_limit_seconds": duel.time_limit_seconds,
        "starts_at": duel.starts_at.isoformat() if duel.starts_at else None,
        "ends_at": duel.ends_at.isoformat() if duel.ends_at else None,
        "started_at": duel.started_at.isoformat() if duel.started_at else None,
        "finished_at": duel.finished_at.isoformat() if duel.finished_at else None,
        "server_time": utcnow().isoformat(),
    }
