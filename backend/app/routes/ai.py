import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user, require_paid
from app.core.ratelimit import rate_limited
from app.db.models import Duel, Submission, User
from app.db.session import get_db
from app.services.judge_service import CodeTooLarge, run_submission
from app.services.ai_service import (
    AIDisabled,
    AIError,
    ai_status,
    opponent_plan,
    review_submission,
)
from app.services.duel_service import DuelNotFound, as_uuid, get_duel
from app.services.problem_service import (
    NoProblemsAvailable,
    pick_random_problem,
    problem_for_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
async def status():
    """What the frontend checks before offering an AI feature."""
    return await ai_status()


@router.post("/duels/{duel_id}/review")
async def review_duel_submission(
    duel_id: str,
    current_user: User = Depends(require_paid),
    db: AsyncSession = Depends(get_db),
):
    """AI review of the caller's own best submission in a finished duel.

    Paid-only, enforced server-side by `require_paid` — the blurred panel in the UI is a
    presentation gate, this is the real one. Deliberately scoped to the caller's own
    submission: reviewing an opponent's code is not a feature.
    """
    try:
        duel = await get_duel(db, duel_id)
    except DuelNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not duel.has_player(current_user.id):
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel.status != "finished":
        raise HTTPException(status_code=409, detail="The duel is not finished yet.")

    result = await db.execute(
        select(Submission)
        .where(
            Submission.duel_id == as_uuid(duel_id),
            Submission.user_id == current_user.id,
        )
        .order_by(Submission.tests_passed.desc(), Submission.submitted_at.desc())
        .limit(1)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="You made no submissions in this duel.")

    try:
        review = await review_submission(db, submission)
    except AIDisabled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except AIError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"submission_id": str(submission.id), "review": review}


@router.post("/opponent/plan")
async def plan_opponent(
    difficulty: str | None = None,
    topic: str | None = None,
    language: str = "python",
    current_user: User = Depends(require_paid),
    db: AsyncSession = Depends(get_db),
):
    """Start an AI practice duel: pick a problem and script the opponent's pacing.

    The plan is generated once, up front, and replayed by the client. One call per
    practice duel rather than one per event — bounded cost, and a network blip mid-duel
    cannot stall the opponent.

    When AI is not configured this still returns a problem and a `scripted: true` plan
    built from a fixed curve. Practice mode working without an API key matters: it is
    the difference between a degraded feature and a broken one.
    """
    try:
        problem = await pick_random_problem(
            db,
            difficulty=None if difficulty in (None, "rank") else difficulty,
            topics=[topic] if topic else None,
            for_users=[current_user.id],
        )
    except NoProblemsAvailable as e:
        raise HTTPException(status_code=404, detail=str(e))

    payload = {
        "problem": await problem_for_client(db, problem.id, language),
        "rating": current_user.rating,
        "time_limit_seconds": settings.duel_time_limit_seconds,
    }

    try:
        payload["plan"] = await opponent_plan(
            problem, current_user.rating, settings.duel_time_limit_seconds
        )
        payload["scripted"] = False
    except (AIDisabled, AIError) as e:
        logger.info("falling back to the scripted opponent: %s", e)
        payload["plan"] = _fallback_plan(current_user.rating, settings.duel_time_limit_seconds)
        payload["scripted"] = True

    return payload


def _fallback_plan(rating: int, limit: int) -> dict:
    """A fixed curve, stretched by rating. Used when the model is unavailable.

    Not as varied as the generated version — it is the same shape every time — but it
    keeps practice mode working, which matters more than variety.
    """
    pace = max(0.55, min(1.6, 1600 / max(rating, 600)))
    raw = [
        (4, "typing", None, None),
        (95, "ran_tests", 1, 2),
        (150, "typing", None, None),
        (260, "ran_tests", 2, 2),
        (300, "submitting", None, None),
        (315, "ran_tests", 4, 5),
        (360, "typing", None, None),
        (470, "submitting", None, None),
        (485, "solved", None, None),
    ]
    steps = []
    for at, state, passed, total in raw:
        moment = int(at * pace)
        if moment > limit:
            continue
        steps.append(
            {"at_seconds": moment, "state": state, "passed": passed, "total": total}
        )
    solve = next((s["at_seconds"] for s in steps if s["state"] == "solved"), 0)
    return {"solve_seconds": solve, "steps": steps}


class PracticeRun(BaseModel):
    problem_id: str
    code: str
    language: str = "python"
    final: bool = False


@router.post("/practice/run")
async def practice_run(
    payload: PracticeRun,
    current_user: User = Depends(require_paid),
    db: AsyncSession = Depends(get_db),
):
    """Judge code in practice mode — the same sandbox, no duel row, no rating.

    Rate-limited separately from duels: practice has no opponent waiting, so a runaway
    loop here would otherwise be a free way to occupy every judge slot.
    """
    limit = (10, 60.0) if payload.final else (25, 60.0)
    if rate_limited(f"practice:{current_user.id}", *limit):
        raise HTTPException(status_code=429, detail="Slow down — too many runs.")

    try:
        outcome = await run_submission(
            db,
            payload.problem_id,
            payload.code,
            language=payload.language,
            public_only=not payload.final,
        )
    except CodeTooLarge:
        raise HTTPException(status_code=413, detail="That submission is too large.")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return outcome
