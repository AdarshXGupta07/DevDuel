import uuid

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # A refresh token must not be usable as an access token — without this check the
    # 7-day token is silently accepted everywhere the 15-minute one is.
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token: malformed user ID")

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.is_banned:
        raise HTTPException(status_code=403, detail=user.banned_reason or "Account suspended")

    return user


async def require_paid(current_user: User = Depends(get_current_user)) -> User:
    """Gate for paid-only features (AI practice, private rooms, full analytics).

    Enforced server-side on every paid path. The frontend hiding a button is a UX
    nicety, not a gate.
    """
    if not current_user.is_paid:
        raise HTTPException(
            status_code=402,
            detail="This feature requires a DevDuel subscription.",
        )
    return current_user
