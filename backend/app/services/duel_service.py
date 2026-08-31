from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Duel

TRANSITIONS = {
    "pending": ["ready", "abandoned"],
    "ready": ["active", "abandoned"],
    "active": ["finished", "abandoned"],
    "finished": [],
    "abandoned": [],
}


class DuelNotFound(Exception):
    pass


class IllegalTransition(Exception):
    pass


def legal_transition(current_status: str, new_status: str) -> None:
    if new_status not in TRANSITIONS.get(current_status, []):
        raise IllegalTransition(f"Illegal status transition from {current_status} to {new_status}")


async def get_duel(db: AsyncSession, duel_id) -> Duel:
    result = await db.execute(select(Duel).where(Duel.id == duel_id))
    duel = result.scalar_one_or_none()
    if duel is None:
        raise DuelNotFound(f"Duel {duel_id} not found.")
    return duel


async def create_duel(db: AsyncSession, player1_id, player2_id, problem_id, duel_id=None) -> Duel:
    duel = Duel(
        id=duel_id,
        player1_id=player1_id,
        player2_id=player2_id,
        problem_id=problem_id,
        status="pending",
    )
    db.add(duel)
    await db.commit()
    await db.refresh(duel)
    return duel


async def transition_duel(db: AsyncSession, duel_id, new_status: str) -> Duel:
    result = await db.execute(select(Duel).where(Duel.id == duel_id))
    duel = result.scalar_one_or_none()
    if duel is None:
        raise DuelNotFound(f"Duel {duel_id} not found.")

    legal_transition(duel.status, new_status)

    duel.status = new_status
    await db.commit()
    await db.refresh(duel)
    return duel


class NotAParticipant(Exception):
    pass


async def mark_ready(db: AsyncSession, duel_id, user_id) -> dict:
    duel = await get_duel(db, duel_id)

    if str(duel.player1_id) == str(user_id):
        ready_field = "player1_ready"
    elif str(duel.player2_id) == str(user_id):
        ready_field = "player2_ready"
    else:
        raise NotAParticipant(f"User {user_id} is not a participant in duel {duel_id}.")

    # Step 1: mark this one player ready. Safe on its own — each player only
    # ever writes their own column, so two different players can never collide here.
    await db.execute(
        update(Duel).where(Duel.id == duel_id).values(**{ready_field: True})
    )
    await db.commit()

    # Step 2: the actual race-safe part. One single UPDATE that both checks
    # "is everything currently true" AND makes the change, in one atomic
    # database operation. If two of these run at nearly the same instant,
    # only ONE can possibly match the WHERE clause and change a row —
    # because the moment the first one commits status='active', the
    # second one's WHERE status='ready' no longer matches anything.
    result = await db.execute(
        update(Duel)
        .where(
            Duel.id == duel_id,
            Duel.status == "ready",
            Duel.player1_ready == True,
            Duel.player2_ready == True,
        )
        .values(status="active", started_at=datetime.utcnow())
    )
    await db.commit()

    started = result.rowcount == 1
    return {"started": started}
