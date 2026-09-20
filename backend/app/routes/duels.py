from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
from app.db.models import Duel, Submission, User
from app.db.session import get_db
from app.services import matchmaking_service as mm
from app.services.analysis_service import build_analysis
from app.services.conduct_service import block_status, clear_block_if_expired
from app.services.duel_service import DuelNotFound, as_uuid, get_duel, serialize_duel
from app.services.problem_service import problem_for_client

router = APIRouter(prefix="/api/duels", tags=["duels"])


@router.get("/me/quota")
async def my_quota(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What the 'N ranked matches left today' badge reads from."""
    await clear_block_if_expired(db, current_user)
    conduct = block_status(current_user)

    if current_user.is_paid:
        return {
            "plan": "paid",
            "ranked_remaining": None,
            "unlimited": True,
            "conduct": conduct,
        }
    return {
        "plan": "free",
        "ranked_remaining": await mm.ranked_remaining_today(db, current_user.id),
        "unlimited": False,
        "resets_timezone": settings.daily_reset_timezone,
        "conduct": conduct,
    }


@router.get("/me/history")
async def my_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Duel)
        .where(
            or_(Duel.player1_id == current_user.id, Duel.player2_id == current_user.id),
            Duel.status == "finished",
        )
        .order_by(Duel.finished_at.desc())
        .limit(min(limit, 100))
    )
    duels = list(result.scalars())

    # One extra query for every opponent name would be an N+1; fetch them in one go.
    opponent_ids = {d.opponent_of(current_user.id) for d in duels}
    opponent_ids.discard(None)
    names: dict[str, str] = {}
    if opponent_ids:
        rows = await db.execute(select(User.id, User.name).where(User.id.in_(opponent_ids)))
        names = {str(i): n for i, n in rows.all()}

    return [
        {
            **serialize_duel(d),
            "opponent": {
                "id": str(d.opponent_of(current_user.id)),
                "name": names.get(str(d.opponent_of(current_user.id)), "Unknown"),
            },
            "result": (
                "draw"
                if d.winner_id is None
                else "win"
                if str(d.winner_id) == str(current_user.id)
                else "loss"
            ),
        }
        for d in duels
    ]


@router.get("/{duel_id}")
async def read_duel(
    duel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The resync endpoint.

    Everything a client needs to redraw the screen after a reconnect, and nothing it is
    not entitled to. A non-participant gets 404, not 403 — no need to confirm that a
    given duel id exists.
    """
    try:
        duel = await get_duel(db, duel_id)
    except DuelNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not duel.has_player(current_user.id):
        raise HTTPException(status_code=404, detail="Duel not found")

    payload = serialize_duel(duel)
    payload["problem"] = await problem_for_client(db, duel.problem_id, duel.language)
    payload["you"] = {
        "id": str(current_user.id),
        "name": current_user.name,
        "rating": current_user.rating,
    }

    opponent = await db.get(User, duel.opponent_of(current_user.id))
    # The client cannot be trusted to decide whether it is being proctored.
    payload["proctor"] = {
        "enabled": settings.proctor_enabled
        and (duel.mode == "ranked" or not settings.proctor_ranked_only),
        "grace_seconds": settings.proctor_grace_seconds,
        "max_violations": settings.proctor_max_violations,
    }

    payload["opponent"] = (
        {"id": str(opponent.id), "name": opponent.name, "rating": opponent.rating}
        if opponent
        else None
    )
    return payload


@router.get("/{duel_id}/analysis")
async def duel_analysis(
    duel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Post-duel analysis for the caller — shown after a win, a loss and a draw.

    The finished-duel check is load-bearing: this response contains the reference
    solution, and serving it mid-duel would hand a player the answer.
    """
    try:
        duel = await get_duel(db, duel_id)
    except DuelNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not duel.has_player(current_user.id):
        raise HTTPException(status_code=404, detail="Duel not found")
    if duel.status != "finished":
        raise HTTPException(status_code=409, detail="The duel is not finished yet.")

    return await build_analysis(db, duel, current_user.id)


@router.get("/{duel_id}/submissions")
async def duel_submissions(
    duel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Post-match reveal.

    Both solutions become visible **only once the duel is finished** — during the match
    this endpoint returns the caller's own submissions and nothing else. That rule is
    the entire reason the duel feels head-to-head without enabling copying.
    """
    try:
        duel = await get_duel(db, duel_id)
    except DuelNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not duel.has_player(current_user.id):
        raise HTTPException(status_code=404, detail="Duel not found")

    query = select(Submission).where(Submission.duel_id == as_uuid(duel_id))
    if duel.status != "finished":
        query = query.where(Submission.user_id == current_user.id)

    result = await db.execute(query.order_by(Submission.submitted_at))
    return [
        {
            "id": str(s.id),
            "user_id": str(s.user_id),
            "language": s.language,
            "verdict": s.verdict,
            "tests_passed": s.tests_passed,
            "tests_total": s.tests_total,
            "runtime_ms": s.runtime_ms,
            "submitted_at": s.submitted_at.isoformat(),
            "code": s.code,
        }
        for s in result.scalars()
    ]
