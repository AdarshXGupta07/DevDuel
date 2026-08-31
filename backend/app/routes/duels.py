from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.db.models import User
from app.schemas.duel import DuelResponse
from app.services.duel_service import get_duel, DuelNotFound

router = APIRouter(prefix="/api/duels", tags=["duels"])


@router.get("/{duel_id}", response_model=DuelResponse)
async def read_duel(
    duel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        duel = await get_duel(db, duel_id)
    except DuelNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return duel
