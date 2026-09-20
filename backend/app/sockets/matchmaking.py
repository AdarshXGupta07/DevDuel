import logging
import uuid

from app.config import settings
from app.db.models import User
from app.db.session import async_session_factory
from app.services import matchmaking_service as mm
from app.services.conduct_service import block_status, clear_block_if_expired
from app.services.duel_service import create_duel, transition_duel
from app.services.problem_service import NoProblemsAvailable, pick_random_problem
from app.sockets.server import sio

logger = logging.getLogger(__name__)


@sio.on("matchmaking:find")
async def matchmaking_find(sid, data=None):
    data = data or {}
    mode = data.get("mode", "casual")
    language = data.get("language", "python")

    if mode not in ("casual", "ranked"):
        await sio.emit("matchmaking:error", {"reason": "invalid_mode"}, to=sid)
        return

    session = await sio.get_session(sid)
    user_id = session["user_id"]

    if mm.is_queued(user_id):
        await sio.emit("matchmaking:error", {"reason": "already_queued"}, to=sid)
        return

    async with async_session_factory() as db:
        user = await db.get(User, uuid.UUID(user_id))
        if user is None:
            return

        # Cooldown check before anything else — including before a ranked slot is
        # claimed, so a blocked player does not silently burn a free match.
        await clear_block_if_expired(db, user)
        block = block_status(user)
        if block["blocked"]:
            await sio.emit(
                "matchmaking:blocked",
                {
                    **block,
                    "message": (
                        f"You left {block['abandons_today']} duels today. "
                        f"Matchmaking is paused for "
                        f"{max(block['seconds_remaining'] // 60, 1)} more minutes."
                    ),
                },
                to=sid,
            )
            return

        # --- the free-tier wall ---
        if mode == "ranked" and not user.is_paid:
            claimed = await mm.claim_ranked_slot(db, user.id)
            if claimed is None:
                await sio.emit(
                    "matchmaking:limit_reached",
                    {
                        "mode": "ranked",
                        "limit": settings.ranked_daily_limit,
                        "resets": f"midnight {settings.daily_reset_timezone}",
                        "message": "You've used today's free ranked matches. "
                        "Upgrade for unlimited ranked play.",
                    },
                    to=sid,
                )
                return

        topics = tuple(t for t in (data.get("topics") or []) if isinstance(t, str))[:6]
        entry = mm.add_to_queue(
            user.id, sid, mode=mode, rating=user.rating, language=language, topics=topics
        )
        remaining = await mm.ranked_remaining_today(db, user.id) if mode == "ranked" else None
        await sio.emit(
            "matchmaking:queued",
            {
                "mode": mode,
                "rating": entry.rating,
                "queue_depth": mm.queue_depth(mode),
                "ranked_remaining_today": None if user.is_paid else remaining,
            },
            to=sid,
        )

        match = mm.try_match(mode)
        if not match:
            return

        try:
            # Both players' histories are excluded: a problem either of them has seen
            # is unfair to the other, not just stale for them.
            problem = await pick_random_problem(
                db,
                topics=match.get("topics"),
                for_users=[match["player1"]["user_id"], match["player2"]["user_id"]],
            )
        except NoProblemsAvailable:
            # Put both players back rather than silently swallowing the match.
            for player in (match["player1"], match["player2"]):
                await sio.emit("matchmaking:error", {"reason": "no_problems"}, to=player["sid"])
            return

        duel_id = match["duel_id"]
        await create_duel(
            db,
            player1_id=match["player1"]["user_id"],
            player2_id=match["player2"]["user_id"],
            problem_id=problem.id,
            duel_id=duel_id,
            mode=match["mode"],
            language=match["language"],
        )
        await transition_duel(db, duel_id, "ready")

    for player in (match["player1"], match["player2"]):
        await sio.enter_room(player["sid"], duel_id)

    await sio.emit(
        "matchmaking:found",
        {
            "duel_id": duel_id,
            "mode": match["mode"],
            "language": match["language"],
            "problem_id": str(problem.id),
            "topics": match.get("topics") or [],
            "matched_topic": problem.tags or [],
            "players": [
                {"user_id": match["player1"]["user_id"], "rating": match["player1"]["rating"]},
                {"user_id": match["player2"]["user_id"], "rating": match["player2"]["rating"]},
            ],
        },
        room=duel_id,
    )
    logger.info("matched %s vs %s (%s) duel=%s",
                match["player1"]["user_id"], match["player2"]["user_id"], mode, duel_id)


@sio.on("matchmaking:cancel")
async def matchmaking_cancel(sid, data=None):
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    was_ranked = mm.queued_mode(user_id) == "ranked"
    mm.remove_from_queue(user_id)

    # A cancelled queue never became a match, so a claimed free slot is refunded.
    if was_ranked and not session.get("is_paid"):
        async with async_session_factory() as db:
            await mm.release_ranked_slot(db, user_id)

    await sio.emit("matchmaking:cancelled", {}, to=sid)
