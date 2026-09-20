"""ELO, the practical version (§7 of the product plan)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Duel, RatingHistory, User

BASE_RATING = 1200
PLACEMENT_MATCHES = 20
K_PLACEMENT = 40
K_STANDARD = 20


def expected_score(rating: int, opponent_rating: int) -> float:
    """Standard ELO logistic expectation: P(this player wins)."""
    return 1.0 / (1.0 + 10 ** ((opponent_rating - rating) / 400.0))


def k_factor(ranked_matches_played: int) -> int:
    """High K while a player is still finding their real rank, then stability."""
    return K_PLACEMENT if ranked_matches_played < PLACEMENT_MATCHES else K_STANDARD


def new_rating(rating: int, opponent_rating: int, actual: float, k: int) -> int:
    """actual: 1.0 win, 0.5 draw, 0.0 loss."""
    return round(rating + k * (actual - expected_score(rating, opponent_rating)))


async def apply_duel_result(db: AsyncSession, duel: Duel) -> dict | None:
    """Update both players' ratings for a finished ranked duel.

    Casual duels never touch rating. Idempotent by construction: it refuses to run twice
    on the same duel because the first run stamps `p1_rating_after`.
    """
    if duel.mode != "ranked":
        return None
    if duel.status != "finished":
        return None
    if duel.p1_rating_after is not None:
        return None  # already rated

    p1 = await db.get(User, duel.player1_id)
    p2 = await db.get(User, duel.player2_id)
    if p1 is None or p2 is None:
        return None

    # A draw where neither player solved the problem tells us nothing about their
    # relative skill, so it must not move ratings (ADR-0044). Standard ELO would still
    # shift them whenever the two ratings differ — the higher-rated player "underperformed
    # by drawing" — which is exactly the wrong lesson to draw from a problem that beat
    # both of them. Ratings stay put, the match is still recorded.
    if duel.winner_id is None and duel.end_reason == "draw":
        duel.p1_rating_before = duel.p1_rating_after = p1.rating
        duel.p2_rating_before = duel.p2_rating_after = p2.rating
        p1.ranked_matches_played += 1
        p2.ranked_matches_played += 1
        await db.commit()
        return {
            str(p1.id): {"before": p1.rating, "after": p1.rating, "delta": 0},
            str(p2.id): {"before": p2.rating, "after": p2.rating, "delta": 0},
        }

    if duel.winner_id is None:
        a1 = a2 = 0.5
    elif str(duel.winner_id) == str(p1.id):
        a1, a2 = 1.0, 0.0
    else:
        a1, a2 = 0.0, 1.0

    k1, k2 = k_factor(p1.ranked_matches_played), k_factor(p2.ranked_matches_played)
    r1_before, r2_before = p1.rating, p2.rating
    r1_after = new_rating(r1_before, r2_before, a1, k1)
    r2_after = new_rating(r2_before, r1_before, a2, k2)

    p1.rating, p2.rating = r1_after, r2_after
    p1.ranked_matches_played += 1
    p2.ranked_matches_played += 1

    duel.p1_rating_before, duel.p1_rating_after = r1_before, r1_after
    duel.p2_rating_before, duel.p2_rating_after = r2_before, r2_after

    db.add_all(
        [
            RatingHistory(
                user_id=p1.id,
                duel_id=duel.id,
                rating_before=r1_before,
                rating_after=r1_after,
                delta=r1_after - r1_before,
                k_factor=k1,
            ),
            RatingHistory(
                user_id=p2.id,
                duel_id=duel.id,
                rating_before=r2_before,
                rating_after=r2_after,
                delta=r2_after - r2_before,
                k_factor=k2,
            ),
        ]
    )
    await db.commit()

    return {
        str(p1.id): {"before": r1_before, "after": r1_after, "delta": r1_after - r1_before},
        str(p2.id): {"before": r2_before, "after": r2_after, "delta": r2_after - r2_before},
    }
