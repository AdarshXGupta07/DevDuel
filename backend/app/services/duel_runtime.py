"""Timers that outlive a single socket event: disconnect grace periods and match clocks.

These live in process memory. If the server restarts mid-duel, every pending timer is
gone and an abandoned duel would sit `active` forever — the same class of gap as the
in-memory queue. `sweep_expired_duels()` is the backstop: it re-resolves anything whose
`ends_at` has passed, so a restart costs latency, not correctness.
"""

import asyncio
import logging
import uuid

from app.config import settings
from app.db.models import utcnow
from app.db.session import async_session_factory
from app.services import matchmaking_service
from app.services.duel_service import (
    DuelNotFound,
    get_duel,
    resolve_on_timeout,
    serialize_duel,
)
from app.services.duel_service import finish_duel as _finish_duel
from app.services.rating_service import apply_duel_result
from app.sockets.server import sio

logger = logging.getLogger(__name__)

# (duel_id, user_id) -> pending forfeit task
_grace_tasks: dict[tuple[str, str], asyncio.Task] = {}
# duel_id -> pending match-clock task
_deadline_tasks: dict[str, asyncio.Task] = {}


def _key(duel_id, user_id) -> tuple[str, str]:
    return (str(duel_id), str(user_id))


# --------------------------------------------------------------------------- finishing


async def finalize(db, duel, detail: dict | None = None) -> dict:
    """Everything that must happen exactly once after a duel is resolved."""
    ratings = await apply_duel_result(db, duel)

    if duel.mode == "ranked":
        for player_id in (duel.player1_id, duel.player2_id):
            await matchmaking_service.mark_ranked_completed(db, player_id)

    payload = serialize_duel(duel)
    payload["ratings"] = ratings
    if detail:
        payload["detail"] = detail

    cancel_deadline(duel.id)
    cancel_all_grace_for_duel(duel.id)

    await sio.emit("duel:end", payload, room=str(duel.id))
    logger.info("duel %s finished: reason=%s winner=%s", duel.id, duel.end_reason, duel.winner_id)
    return payload


# --------------------------------------------------------------------- grace / forfeit


async def _forfeit_after_grace(duel_id: str, user_id: str) -> None:
    try:
        await asyncio.sleep(settings.disconnect_grace_seconds)
    except asyncio.CancelledError:
        # The player came back in time. This is the normal, happy path.
        raise

    try:
        async with async_session_factory() as db:
            duel = await get_duel(db, duel_id)
            if duel.status != "active":
                return
            opponent_id = duel.opponent_of(user_id)
            finished = await _finish_duel(db, duel_id, opponent_id, "disconnect")
            if finished is None:
                return  # someone else resolved it first; nothing to do

            # A disconnect that never came back counts the same as a deliberate quit.
            # Pulling the cable must not be cheaper than pressing the button.
            from app.services.conduct_service import record_abandon

            await record_abandon(db, uuid.UUID(str(user_id)))
            await finalize(db, finished, {"forfeited_by": str(user_id)})
    except DuelNotFound:
        return
    except Exception:  # noqa: BLE001 — a background task must never die silently
        logger.exception("grace-period forfeit failed for duel %s", duel_id)
    finally:
        _grace_tasks.pop(_key(duel_id, user_id), None)


def start_grace_timer(duel_id, user_id) -> None:
    """Start the countdown to a forfeit. Idempotent per (duel, player)."""
    key = _key(duel_id, user_id)
    if key in _grace_tasks and not _grace_tasks[key].done():
        return
    _grace_tasks[key] = asyncio.create_task(_forfeit_after_grace(str(duel_id), str(user_id)))


def cancel_grace_timer(duel_id, user_id) -> bool:
    """Stop a pending forfeit. Returns True if there was one to stop."""
    task = _grace_tasks.pop(_key(duel_id, user_id), None)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def cancel_all_grace_for_duel(duel_id) -> None:
    prefix = str(duel_id)
    for key in [k for k in _grace_tasks if k[0] == prefix]:
        task = _grace_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()


def has_pending_grace(duel_id, user_id) -> bool:
    task = _grace_tasks.get(_key(duel_id, user_id))
    return task is not None and not task.done()


# ------------------------------------------------------------------------ match clock


async def _expire_at_deadline(duel_id: str, seconds: float) -> None:
    try:
        await asyncio.sleep(max(seconds, 0))
    except asyncio.CancelledError:
        raise

    try:
        async with async_session_factory() as db:
            duel = await get_duel(db, duel_id)
            if duel.status != "active":
                return
            finished, detail = await resolve_on_timeout(db, duel_id)
            if finished is None:
                return
            await finalize(db, finished, detail)
    except DuelNotFound:
        return
    except Exception:  # noqa: BLE001
        logger.exception("deadline resolution failed for duel %s", duel_id)
    finally:
        _deadline_tasks.pop(str(duel_id), None)


def schedule_deadline(duel_id, ends_at) -> None:
    key = str(duel_id)
    existing = _deadline_tasks.get(key)
    if existing and not existing.done():
        return
    seconds = (ends_at - utcnow()).total_seconds()
    _deadline_tasks[key] = asyncio.create_task(_expire_at_deadline(key, seconds))


def cancel_deadline(duel_id) -> None:
    task = _deadline_tasks.pop(str(duel_id), None)
    if task and not task.done():
        task.cancel()


# --------------------------------------------------------------------------- restart backstop


async def sweep_expired_duels() -> int:
    """Resolve duels whose clock expired while no timer existed (e.g. after a restart)."""
    from sqlalchemy import select

    from app.db.models import Duel

    resolved = 0
    async with async_session_factory() as db:
        result = await db.execute(
            select(Duel).where(Duel.status == "active", Duel.ends_at < utcnow())
        )
        for duel in result.scalars():
            finished, detail = await resolve_on_timeout(db, duel.id)
            if finished is not None:
                await finalize(db, finished, detail)
                resolved += 1
    if resolved:
        logger.info("swept %s expired duels", resolved)
    return resolved
