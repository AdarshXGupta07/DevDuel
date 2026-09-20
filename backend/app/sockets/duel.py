"""In-duel socket events.

The rule that shapes this whole file: **opponent code never leaves the server until the
duel is finished.** Status events carry progress, never source.
"""

import logging
import uuid
from collections import defaultdict

from app.core.ratelimit import rate_limited

from app.config import settings
from app.db.models import MatchEvent, utcnow
from app.db.session import async_session_factory
from app.services import duel_runtime
from app.services.conduct_service import record_abandon
from app.services.duel_service import (
    DuelNotFound,
    NotAParticipant,
    finish_duel,
    get_duel,
    mark_ready,
    serialize_duel,
)
from app.services.judge_service import CodeTooLarge, judge_and_record, run_submission
from app.services.problem_service import problem_for_client
from app.services.sandbox import supported_languages
from app.sockets.server import sio

logger = logging.getLogger(__name__)

# Rate limits: enough to stop a player brute-forcing hidden test cases by resubmitting
# in a loop, and to stop the judge being a free compute farm.
_SUBMIT_LIMIT = (6, 60.0)   # 6 submissions per 60s
_RUN_LIMIT = (20, 60.0)     # 20 sample runs per 60s


def _rate_limited(key: str, limit: tuple[int, float]) -> bool:
    count, window = limit
    return rate_limited(key, count, window)


async def _participant_duel(sid, duel_id):
    """Load a duel and prove this socket's user is actually in it."""
    session = await sio.get_session(sid)
    user_id = session["user_id"]
    async with async_session_factory() as db:
        duel = await get_duel(db, duel_id)
        if not duel.has_player(user_id):
            raise NotAParticipant(f"User {user_id} is not in duel {duel_id}")
    return session, user_id, duel


@sio.on("duel:join")
async def duel_join(sid, data):
    """Explicit room join + resync. The client calls this after any (re)connect."""
    try:
        session, user_id, duel = await _participant_duel(sid, data.get("duel_id"))
    except (DuelNotFound, NotAParticipant):
        await sio.emit("duel:error", {"reason": "not_found"}, to=sid)
        return

    await sio.enter_room(sid, str(duel.id))
    async with async_session_factory() as db:
        payload = serialize_duel(duel)
        payload["problem"] = await problem_for_client(db, duel.problem_id, duel.language)
    await sio.emit("duel:state", payload, to=sid)


@sio.on("duel:ready")
async def duel_ready(sid, data):
    duel_id = data["duel_id"]
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    async with async_session_factory() as db:
        try:
            result = await mark_ready(db, duel_id, user_id)
        except (NotAParticipant, DuelNotFound):
            await sio.emit("duel:error", {"reason": "not_a_participant"}, to=sid)
            return

        await sio.emit(
            "duel:ready_state",
            {"duel_id": str(duel_id), "user_id": user_id},
            room=str(duel_id),
        )

        if not result["started"]:
            return

        duel = await get_duel(db, duel_id)
        payload = serialize_duel(duel)
        payload["problem"] = await problem_for_client(db, duel.problem_id, duel.language)

    # The client counts down to `starts_at` and up to `ends_at` locally. The server
    # sends timestamps, never ticks — a tick stream is wrong for every client by
    # exactly its own network delay, and unrecoverable after a refresh.
    await sio.emit("duel:start", payload, room=str(duel_id))
    duel_runtime.schedule_deadline(duel.id, duel.ends_at)


@sio.on("duel:status")
async def duel_status(sid, data):
    """Relay a player's progress to their opponent. Never carries code."""
    duel_id = data.get("duel_id")
    state = str(data.get("state", ""))[:32]
    if state not in ("typing", "idle", "running", "ran_tests", "submitting"):
        return

    session = await sio.get_session(sid)
    payload = {
        "duel_id": duel_id,
        "user_id": session["user_id"],
        "state": state,
    }
    # Only the aggregate is allowed through, and only as integers.
    if "passed" in data and "total" in data:
        try:
            payload["passed"] = int(data["passed"])
            payload["total"] = int(data["total"])
        except (TypeError, ValueError):
            pass

    await sio.emit("duel:opponent_status", payload, room=str(duel_id), skip_sid=sid)


def _chosen_language(data, duel):
    """Each player picks their own language; the duel's is only the default.

    The problem is language-agnostic — stdin in, stdout out — so there is no reason to
    force both players into one. Anything not offered by the judge falls back to the
    duel default rather than erroring, so a stale client cannot wedge a submission.
    """
    requested = (data or {}).get("language")
    return requested if requested in {l["id"] for l in supported_languages()} else duel.language


@sio.on("duel:run")
async def duel_run(sid, data):
    """The editor's Run button: sample cases only, nothing persisted, no win condition."""
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    if _rate_limited(f"run:{user_id}", _RUN_LIMIT):
        await sio.emit("duel:error", {"reason": "rate_limited"}, to=sid)
        return

    try:
        _, _, duel = await _participant_duel(sid, data.get("duel_id"))
    except (DuelNotFound, NotAParticipant):
        await sio.emit("duel:error", {"reason": "not_a_participant"}, to=sid)
        return

    if duel.status != "active":
        await sio.emit("duel:error", {"reason": "duel_not_active"}, to=sid)
        return

    async with async_session_factory() as db:
        try:
            outcome = await run_submission(
                db,
                duel.problem_id,
                data.get("code", ""),
                language=_chosen_language(data, duel),
                public_only=True,
            )
        except CodeTooLarge:
            await sio.emit("duel:error", {"reason": "code_too_large"}, to=sid)
            return

    await sio.emit("duel:run_result", outcome, to=sid)
    await sio.emit(
        "duel:opponent_status",
        {
            "duel_id": str(duel.id),
            "user_id": user_id,
            "state": "ran_tests",
            "passed": outcome["tests_passed"],
            "total": outcome["tests_total"],
        },
        room=str(duel.id),
        skip_sid=sid,
    )


@sio.on("duel:submit")
async def duel_submit(sid, data):
    session = await sio.get_session(sid)
    user_id = session["user_id"]

    if _rate_limited(f"submit:{user_id}", _SUBMIT_LIMIT):
        await sio.emit("duel:error", {"reason": "rate_limited"}, to=sid)
        return

    try:
        _, _, duel = await _participant_duel(sid, data.get("duel_id"))
    except (DuelNotFound, NotAParticipant):
        await sio.emit("duel:error", {"reason": "not_a_participant"}, to=sid)
        return

    if duel.status != "active":
        await sio.emit("duel:error", {"reason": "duel_not_active"}, to=sid)
        return
    if duel.ends_at and utcnow() > duel.ends_at:
        await sio.emit("duel:error", {"reason": "time_expired"}, to=sid)
        return

    await sio.emit(
        "duel:opponent_status",
        {"duel_id": str(duel.id), "user_id": user_id, "state": "submitting"},
        room=str(duel.id),
        skip_sid=sid,
    )

    async with async_session_factory() as db:
        try:
            submission, outcome = await judge_and_record(
                db,
                duel_id=duel.id,
                user_id=uuid.UUID(user_id),
                problem_id=duel.problem_id,
                code=data.get("code", ""),
                language=_chosen_language(data, duel),
            )
        except CodeTooLarge:
            await sio.emit("duel:error", {"reason": "code_too_large"}, to=sid)
            return

        await sio.emit(
            "duel:submission_result",
            {
                "duel_id": str(duel.id),
                "submission_id": str(submission.id),
                "verdict": outcome["verdict"],
                "tests_passed": outcome["tests_passed"],
                "tests_total": outcome["tests_total"],
                "runtime_ms": outcome["runtime_ms"],
                "stderr": outcome["stderr"],
                # Hidden-case detail is stripped inside run_submission.
                "results": outcome["results"],
            },
            to=sid,
        )

        await sio.emit(
            "duel:opponent_status",
            {
                "duel_id": str(duel.id),
                "user_id": user_id,
                "state": "ran_tests",
                "passed": outcome["tests_passed"],
                "total": outcome["tests_total"],
            },
            room=str(duel.id),
            skip_sid=sid,
        )

        if outcome["verdict"] != "accepted":
            return

        # First fully-passing submission wins. `finish_duel` is the atomic gate: if both
        # players' submissions are accepted within the same instant, exactly one of these
        # calls changes a row and the other returns None.
        finished = await finish_duel(db, duel.id, uuid.UUID(user_id), "solved")
        if finished is None:
            return
        await duel_runtime.finalize(db, finished, {"solved_by": user_id})


@sio.on("duel:forfeit")
async def duel_forfeit(sid, data):
    """Deliberate quit. Always allowed — but it counts.

    Trapping someone in a match they want to leave is worse than letting them go; what
    it must not be is free, or every losing position becomes "just leave".
    """
    try:
        session, user_id, duel = await _participant_duel(sid, data.get("duel_id"))
    except (DuelNotFound, NotAParticipant):
        return

    async with async_session_factory() as db:
        opponent_id = duel.opponent_of(user_id)
        finished = await finish_duel(db, duel.id, opponent_id, "forfeit")
        if finished is None:
            return

        penalty = await record_abandon(db, uuid.UUID(user_id))
        await duel_runtime.finalize(db, finished, {"forfeited_by": user_id})

    # Tell the quitter privately what it cost them — the opponent does not need to know.
    await sio.emit("duel:forfeit_penalty", penalty, to=sid)


# Proctoring violations per (duel, player). In-process like everything else here; the
# consequence is durable (the forfeit lands in Postgres) even though the tally is not.
_violations: dict[tuple[str, str], int] = defaultdict(int)


@sio.on("duel:violation")
async def duel_violation(sid, data):
    """The client reporting that the player left the duel window.

    Worth being honest about what this is: the *client* decides whether to report. A
    determined cheat simply patches this out, exactly like paste-disable. What it does
    buy is a real deterrent for the 95% who would otherwise casually alt-tab to an LLM,
    and a behavioural record for the rest.

    The decision to forfeit is made here, not in the browser — the client reports events,
    the server decides consequences.
    """
    duel_id = data.get("duel_id")
    kind = str(data.get("kind", "blur"))[:32]
    returned = bool(data.get("returned"))

    try:
        session, user_id, duel = await _participant_duel(sid, duel_id)
    except (DuelNotFound, NotAParticipant):
        return

    if duel.status != "active":
        return
    if settings.proctor_ranked_only and duel.mode != "ranked":
        return

    key = (str(duel.id), str(user_id))
    _violations[key] += 1
    count = _violations[key]

    async with async_session_factory() as db:
        db.add(
            MatchEvent(
                duel_id=duel.id,
                user_id=uuid.UUID(user_id),
                seq=-count,  # negative sequence keeps these out of the keystroke stream
                kind=f"proctor_{kind}",
                payload={"count": count, "returned": returned},
            )
        )
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()

        over_limit = count > settings.proctor_max_violations
        if returned and not over_limit:
            await sio.emit(
                "duel:violation_warning",
                {
                    "count": count,
                    "max": settings.proctor_max_violations,
                    "message": (
                        f"Leaving the duel window is not allowed in ranked matches. "
                        f"{settings.proctor_max_violations - count + 1} more and the "
                        f"match is forfeited."
                    ),
                },
                to=sid,
            )
            return

        # Either they never came back within the grace period, or they have used up
        # every warning. Same outcome.
        opponent_id = duel.opponent_of(user_id)
        finished = await finish_duel(db, duel.id, opponent_id, "forfeit")
        if finished is None:
            return

        await record_abandon(db, uuid.UUID(user_id))
        await sio.emit(
            "duel:violation_forfeit",
            {"reason": "left_duel_window", "count": count},
            to=sid,
        )
        await duel_runtime.finalize(
            db, finished, {"forfeited_by": user_id, "cause": "proctor"}
        )
        logger.info("proctor forfeit: duel=%s user=%s violations=%s", duel.id, user_id, count)

    _violations.pop(key, None)


@sio.on("duel:events")
async def duel_events(sid, data):
    """Batched behavioural events for anti-cheat (§6 Layer 2).

    Logged from day one even though nothing analyses it yet — the historical data is the
    whole point, and it cannot be collected retroactively. Clients flush every ~2s.
    """
    duel_id = data.get("duel_id")
    events = data.get("events") or []
    if not duel_id or not isinstance(events, list):
        return

    session = await sio.get_session(sid)
    user_id = session["user_id"]

    rows = []
    for event in events[:200]:
        try:
            rows.append(
                MatchEvent(
                    duel_id=uuid.UUID(str(duel_id)),
                    user_id=uuid.UUID(user_id),
                    seq=int(event["seq"]),
                    kind=str(event["kind"])[:40],
                    payload=event.get("payload"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return

    async with async_session_factory() as db:
        db.add_all(rows)
        try:
            await db.commit()
        except Exception:  # noqa: BLE001 — a duplicate seq must never break a duel
            await db.rollback()
            logger.warning("match_event batch rejected for duel %s", duel_id)
