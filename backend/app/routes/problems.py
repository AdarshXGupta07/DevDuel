from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.models import Problem, User
from app.db.session import get_db
from app.services.problem_service import (
    NoProblemsAvailable,
    available_topics,
    problem_for_client,
)
from app.services.sandbox import supported_languages

router = APIRouter(prefix="/api", tags=["problems"])


@router.get("/languages")
async def languages():
    """Single source of truth for the language list.

    The frontend reads this rather than hardcoding options, so adding a language is a
    backend change only — and a selector can never offer something the judge cannot run.
    """
    return {"languages": supported_languages()}


@router.get("/topics")
async def topics(db: AsyncSession = Depends(get_db)):
    """Topics the queue can actually honour — derived from the problem bank, not a list."""
    return {"topics": await available_topics(db)}


@router.get("/problems")
async def list_problems(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Catalogue view. Statements and test data are deliberately not included."""
    result = await db.execute(
        select(Problem).where(Problem.is_active.is_(True)).order_by(Problem.title)
    )
    return [
        {
            "id": str(p.id),
            "slug": p.slug,
            "title": p.title,
            "difficulty": p.difficulty,
            "tags": p.tags or [],
        }
        for p in result.scalars()
    ]


@router.get("/problems/{problem_id}")
async def read_problem(
    problem_id: str,
    language: str = "python",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await problem_for_client(db, problem_id, language)
    except NoProblemsAvailable as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/leaderboard")
async def leaderboard(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Public. Backed by ix_users_rating."""
    result = await db.execute(
        select(User)
        .where(User.deleted_at.is_(None), User.is_banned.is_(False))
        .order_by(User.rating.desc())
        .limit(min(limit, 200))
    )
    return [
        {
            "rank": i,
            "id": str(u.id),
            "name": u.name,
            "rating": u.rating,
            "ranked_matches_played": u.ranked_matches_played,
        }
        for i, u in enumerate(result.scalars(), start=1)
    ]
