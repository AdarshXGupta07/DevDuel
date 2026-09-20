"""Rage-quit deterrent.

Quitting a live duel is always allowed — trapping someone in a match they want to leave
is worse product design than letting them go. What it must not be is *free*: an
unpunished quit turns every losing position into "just leave", which ruins the match for
the opponent who was winning.

So: a forfeit costs the match (and rating, if ranked), and repeated forfeits in one day
cost a cooldown. Counted per day so that a bad afternoon does not follow someone forever.
"""

import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import User, utcnow
from app.services.matchmaking_service import local_usage_date

logger = logging.getLogger(__name__)


def _cooldown_for(abandons: int) -> timedelta | None:
    """Escalating cooldown, starting at the configured threshold.

    Doubling rather than a flat penalty: the first offence is usually a bad connection
    or a misclick, the fourth in one day is a habit.
    """
    threshold = settings.abandon_threshold
    if abandons < threshold:
        return None
    steps = abandons - threshold           # 0, 1, 2, ...
    minutes = settings.abandon_cooldown_minutes * (2 ** min(steps, 3))  # cap the doubling
    return timedelta(minutes=minutes)


async def record_abandon(db: AsyncSession, user_id) -> dict:
    """Count one abandoned duel against a player. Returns the resulting penalty, if any."""
    user = await db.get(User, user_id)
    if user is None:
        return {"abandons": 0, "blocked_until": None}

    today = local_usage_date()
    if user.abandons_date != today:
        user.abandons_date = today
        user.abandons_today = 0

    user.abandons_today += 1
    cooldown = _cooldown_for(user.abandons_today)
    if cooldown is not None:
        user.matchmaking_blocked_until = utcnow() + cooldown
        logger.info(
            "matchmaking cooldown for %s: %s abandons today, blocked %s minutes",
            user_id,
            user.abandons_today,
            int(cooldown.total_seconds() // 60),
        )

    await db.commit()
    return {
        "abandons": user.abandons_today,
        "blocked_until": (
            user.matchmaking_blocked_until.isoformat()
            if user.matchmaking_blocked_until
            else None
        ),
    }


def block_status(user: User) -> dict:
    """Is this player in a cooldown right now, and for how much longer?"""
    today = local_usage_date()
    abandons = user.abandons_today if user.abandons_date == today else 0

    until = user.matchmaking_blocked_until
    if until is None or until <= utcnow():
        return {
            "blocked": False,
            "abandons_today": abandons,
            "remaining_before_block": max(settings.abandon_threshold - abandons, 0),
            "seconds_remaining": 0,
            "blocked_until": None,
        }

    return {
        "blocked": True,
        "abandons_today": abandons,
        "remaining_before_block": 0,
        "seconds_remaining": int((until - utcnow()).total_seconds()),
        "blocked_until": until.isoformat(),
    }


async def clear_block_if_expired(db: AsyncSession, user: User) -> None:
    """Tidy up an expired block so the column does not stay set forever."""
    if user.matchmaking_blocked_until and user.matchmaking_blocked_until <= utcnow():
        user.matchmaking_blocked_until = None
        await db.commit()
