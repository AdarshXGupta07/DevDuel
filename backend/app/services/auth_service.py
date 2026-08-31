import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import User, RefreshToken
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from jose import JWTError


class EmailAlreadyExists(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidToken(Exception):
    pass


async def register_user(db: AsyncSession, name: str, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise EmailAlreadyExists(f"Email {email} is already registered.")
    hashed = await asyncio.to_thread(hash_password, password)
    new_user = User(name=name, email=email, password_hash=hashed)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise InvalidCredentials("Invalid email or password.")

    is_valid = await asyncio.to_thread(verify_password, password, user.password_hash)
    if not is_valid:
        raise InvalidCredentials("Invalid email or password.")

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))

    db_token = RefreshToken(user_id=user.id, token=refresh_token)
    db.add(db_token)
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


async def refresh_access_token(db: AsyncSession, token: str) -> dict:
    try:
        payload = decode_token(token)
    except JWTError:
        raise InvalidToken("Refresh token is invalid or expired.")

    if payload.get("type") != "refresh":
        raise InvalidToken("Token is not a refresh token.")

    result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
    db_token = result.scalar_one_or_none()

    if db_token is None or db_token.revoked:
        raise InvalidToken("Refresh token is invalid or has been revoked.")

    new_access_token = create_access_token(payload["sub"])
    return {"access_token": new_access_token}


async def logout_user(db: AsyncSession, token: str) -> None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.token == token))
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise InvalidToken("Refresh token not found.")

    db_token.revoked = True
    await db.commit()
async def updateprofile(db:AsyncSession,user_id:str,new_name:str,new_email:str)->User:
    result=await db.execute(select(User).where(User.id==user_id))
    user=result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")
    
    # Check if the new email is already taken by another user
    if new_email != user.email:
        email_check=await db.execute(select(User).where(User.email==new_email))
        existing_user=email_check.scalar_one_or_none()
        if existing_user:
            raise EmailAlreadyExists(f"Email {new_email} is already registered.")

    user.name=new_name
    user.email=new_email
    await db.commit()
    await db.refresh(user)
    return user


async def updatepassword(db:AsyncSession,user_id:str,current_password:str,new_password:str)->User:
    result=await db.execute(select(User).where(User.id==user_id))
    user=result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")

    is_valid = await asyncio.to_thread(verify_password, current_password, user.password_hash)
    if not is_valid:
        raise InvalidCredentials("Current password is incorrect.")

    hashed=await asyncio.to_thread(hash_password,new_password)
    user.password_hash=hashed
    await db.commit()
    await db.refresh(user)
    return user

async def deleteuser(db:AsyncSession,user_id:str)->None:
    result=await db.execute(select(User).where(User.id==user_id))
    user=result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")
    
    await db.delete(user)
    await db.commit()