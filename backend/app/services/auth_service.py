import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import User
from app.core.security import hash_password

class EmailAlreadyExists(Exception):
    pass

async def register_user(db: AsyncSession, name: str, email: str, password: str) -> User:
    result=await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise EmailAlreadyExists(f"Email {email} is already registered.")
    hashed = await asyncio.to_thread(hash_password, password)
    new_user = User(name=name, email=email, password_hash=hashed)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user