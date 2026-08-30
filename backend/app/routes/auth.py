from fastapi import Depends, HTTPException, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.auth_service import register_user, EmailAlreadyExists
from app.db.session import get_db
from app.schemas.user import UserAccept, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse)
async def register(user: UserAccept, db: AsyncSession = Depends(get_db)):
    try:
        new_user = await register_user(db, user.name, user.email, user.password)
    except EmailAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e))
    return new_user