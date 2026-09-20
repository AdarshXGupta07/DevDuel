"""Matchmaking queue and the free-tier ranked cap.

The queue is a per-process dict, which means: it dies with the process, and two API
instances have two queues that cannot see each other. That is a known, accepted
limitation until Day 25 moves it to Redis (ADR-0015). The cap, by contrast, lives in
Postgres from the start — it is money-adjacent, so it has to be correct across restarts
and instances.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import utcnow

# Ranked pairing starts tight and widens the longer someone waits, so a thin queue
# still matches eventually instead of leaving a player spinning forever.
INITIAL_RATING_WINDOW = 100
WINDOW_GROWTH_PER_SECOND = 10
MAX_RATING_WINDOW = 1000


@dataclass
class QueueEntry:
    user_id: str
    sid: str
    mode: str
    rating: int
    language: str = "python"
    # Preferred data-structure topics, empty meaning "anything".
    topics: tuple[str, ...] = ()
    joined_at: datetime = field(default_factory=utcnow)

    def window(self, now: datetime | None = None) -> int:
        waited = ((now or utcnow()) - self.joined_at).total_seconds()
        return min(
            MAX_RATING_WINDOW,
            int(INITIAL_RATING_WINDOW + waited * WINDOW_GROWTH_PER_SECOND),
        )


# mode -> {user_id: QueueEntry}
_queues: dict[str, dict[str, QueueEntry]] = {"casual": {}, "ranked": {}}


def add_to_queue(user_id, sid: str, mode: str = "casual", rating: int = 1200,
                 language: str = "python", topics: tuple[str, ...] = ()) -> QueueEntry:
    entry = QueueEntry(
        user_id=str(user_id),
        sid=sid,
        mode=mode,
        rating=rating,
        language=language,
        topics=tuple(topics or ()),
    )
    _queues[mode][str(user_id)] = entry
    return entry


def remove_from_queue(user_id) -> None:
    for queue in _queues.values():
        queue.pop(str(user_id), None)


def is_queued(user_id) -> bool:
    return any(str(user_id) in queue for queue in _queues.values())


def queued_mode(user_id) -> str | None:
    """Which queue this user is sitting in, if any."""
    for mode, queue in _queues.items():
        if str(user_id) in queue:
            return mode
    return None


def queue_depth(mode: str | None = None) -> int:
    if mode:
        return len(_queues.get(mode, {}))
    return sum(len(q) for q in _queues.values())


def clear_queues() -> None:
    for queue in _queues.values():
        queue.clear()


def try_match(mode: str = "casual") -> dict | None:
    """Pair two waiting players, removing both from the queue.

    Casual: anyone with anyone — depth matters more than fairness.
    Ranked: closest rating pair whose windows both accept the gap.
    """
    queue = _queues[mode]
    if len(queue) < 2:
        return None

    now = utcnow()
    entries = sorted(queue.values(), key=lambda e: e.rating)

    best: tuple[QueueEntry, QueueEntry] | None = None
    if mode == "casual":
        # Longest-waiting two.
        by_wait = sorted(queue.values(), key=lambda e: e.joined_at)
        best = (by_wait[0], by_wait[1])
    else:
        best_gap = None
        for a, b in zip(entries, entries[1:]):
            gap = abs(a.rating - b.rating)
            if gap <= min(a.window(now), b.window(now)) and (best_gap is None or gap < best_gap):
                best_gap, best = gap, (a, b)

    if best is None:
        return None

    first, second = best
    del queue[first.user_id]
    del queue[second.user_id]

    return {
        "duel_id": str(uuid.uuid4()),
        "mode": mode,
        "language": first.language,
        "topics": agreed_topics(first.topics, second.topics),
        "player1": {
            "user_id": first.user_id,
            "sid": first.sid,
            "rating": first.rating,
            "language": first.language,
            "topics": list(first.topics),
        },
        "player2": {
            "user_id": second.user_id,
            "sid": second.sid,
            "rating": second.rating,
            "language": second.language,
            "topics": list(second.topics),
        },
    }


def agreed_topics(a: tuple[str, ...], b: tuple[str, ...]) -> list[str]:
    """Which topics the problem should be drawn from, given two players' preferences.

    The rule, in order:
      1. Both picked topics and they overlap → use the overlap. Both got what they asked.
      2. Only one picked → use theirs. Their opponent had no opinion to override.
      3. Both picked but nothing overlaps → use the union, so each has a real chance of
         getting something they wanted rather than neither of them getting anything.
      4. Nobody picked → no constraint.

    Case 3 is the interesting one. Refusing to match players with different interests
    would protect a preference at the cost of the thing they actually came for, which is
    a duel — and in a thin queue it would mean never matching at all.
    """
    if a and b:
        overlap = [t for t in a if t in set(b)]
        if overlap:
            return overlap
        return list(dict.fromkeys([*a, *b]))
    return list(a or b)


# --------------------------------------------------------------------------- daily cap


@lru_cache(maxsize=4)
def _reset_zone(name: str) -> ZoneInfo:
    """Resolve the reset timezone once, with an error that says how to fix it.

    Windows ships no IANA timezone database, so `ZoneInfo("Asia/Kolkata")` raises there
    unless the `tzdata` package is installed. Falling back to UTC would be worse than
    failing: it would silently move every user's daily reset by five and a half hours.
    """
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as e:
        raise RuntimeError(
            f"Timezone {name!r} is unavailable. On Windows this means the IANA database "
            f"is missing — install it with `pip install tzdata`."
        ) from e


def local_usage_date(now: datetime | None = None) -> date:
    """Today's date at the configured reset timezone (fixed IST midnight, ADR-0024).

    Fixed reset rather than rolling 24h: simpler to build, far simpler to explain in the
    UI ("resets at midnight"), and it does not require storing a per-user timer.
    """
    tz = _reset_zone(settings.daily_reset_timezone)
    return (now or datetime.now(timezone.utc)).astimezone(tz).date()


_CLAIM_SQL = text(
    """
    INSERT INTO ranked_daily_usage (user_id, usage_date, matches_started, updated_at)
    VALUES (:user_id, :usage_date, 1, now())
    ON CONFLICT (user_id, usage_date) DO UPDATE
        SET matches_started = ranked_daily_usage.matches_started + 1,
            updated_at = now()
        WHERE ranked_daily_usage.matches_started < :limit
    RETURNING matches_started
    """
)


async def claim_ranked_slot(db: AsyncSession, user_id, limit: int | None = None) -> int | None:
    """Atomically consume one of today's free ranked matches.

    Returns the new count, or None when the cap is already spent. This is Day 9's trick
    again: the check and the act are one statement, so two tabs clicking "Ranked" at the
    same instant cannot both get the last slot. A paid user never calls this.
    """
    limit = settings.ranked_daily_limit if limit is None else limit
    result = await db.execute(
        _CLAIM_SQL,
        {
            "user_id": str(uuid.UUID(str(user_id))),
            "usage_date": local_usage_date(),
            "limit": limit,
        },
    )
    row = result.first()
    await db.commit()
    return None if row is None else int(row[0])


_RELEASE_SQL = text(
    """
    UPDATE ranked_daily_usage
       SET matches_started = GREATEST(matches_started - 1, 0), updated_at = now()
     WHERE user_id = :user_id AND usage_date = :usage_date
    """
)


async def release_ranked_slot(db: AsyncSession, user_id, usage_date: date | None = None) -> None:
    """Give a slot back when a match never actually happened.

    Per the product plan: only a *completed* match should burn a free attempt, so a
    disconnect during ready-up, or a queue cancel, refunds the claim.
    """
    await db.execute(
        _RELEASE_SQL,
        {"user_id": str(uuid.UUID(str(user_id))), "usage_date": usage_date or local_usage_date()},
    )
    await db.commit()


_COMPLETE_SQL = text(
    """
    UPDATE ranked_daily_usage
       SET matches_completed = matches_completed + 1, updated_at = now()
     WHERE user_id = :user_id AND usage_date = :usage_date
    """
)


async def mark_ranked_completed(db: AsyncSession, user_id) -> None:
    await db.execute(
        _COMPLETE_SQL, {"user_id": str(uuid.UUID(str(user_id))), "usage_date": local_usage_date()}
    )
    await db.commit()


_REMAINING_SQL = text(
    """
    SELECT COALESCE(matches_started, 0)
      FROM ranked_daily_usage
     WHERE user_id = :user_id AND usage_date = :usage_date
    """
)


async def ranked_remaining_today(db: AsyncSession, user_id) -> int:
    result = await db.execute(
        _REMAINING_SQL,
        {"user_id": str(uuid.UUID(str(user_id))), "usage_date": local_usage_date()},
    )
    row = result.first()
    used = int(row[0]) if row else 0
    return max(settings.ranked_daily_limit - used, 0)
