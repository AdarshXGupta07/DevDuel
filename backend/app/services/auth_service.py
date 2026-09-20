import asyncio
import secrets
import uuid

from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    token_expiry,
    utcnow,
    verify_password,
)
from app.db.models import RefreshToken, User


class EmailAlreadyExists(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidToken(Exception):
    pass


class AccountBanned(Exception):
    pass


async def register_user(db: AsyncSession, name: str, email: str, password: str) -> User:
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise EmailAlreadyExists(f"Email {email} is already registered.")

    hashed = await asyncio.to_thread(hash_password, password)
    new_user = User(name=name, email=email, password_hash=hashed)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


async def _issue_refresh_token(
    db: AsyncSession,
    user_id,
    family_id: uuid.UUID | None = None,
) -> tuple[str, RefreshToken]:
    """Mint a refresh token and persist only its hash."""
    raw = create_refresh_token(str(user_id))
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_token(raw),
        family_id=family_id or uuid.uuid4(),
        expires_at=token_expiry(raw),
    )
    db.add(row)
    await db.flush()
    return raw, row


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or user.deleted_at is not None:
        # Still burn a hash so a missing account and a wrong password take the same time.
        await asyncio.to_thread(verify_password, password, _DUMMY_HASH)
        raise InvalidCredentials("Invalid email or password.")

    is_valid = await asyncio.to_thread(verify_password, password, user.password_hash)
    if not is_valid:
        raise InvalidCredentials("Invalid email or password.")

    if user.is_banned:
        raise AccountBanned(user.banned_reason or "This account has been suspended.")

    access_token = create_access_token(str(user.id))
    refresh_token, _ = await _issue_refresh_token(db, user.id)
    user.last_seen_at = utcnow()
    await db.commit()

    return {"access_token": access_token, "refresh_token": refresh_token}


# A real bcrypt hash of a random string, used only to equalise login timing.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


async def _revoke_family(db: AsyncSession, family_id) -> None:
    await db.execute(
        update(RefreshToken).where(RefreshToken.family_id == family_id).values(revoked=True)
    )


async def refresh_access_token(db: AsyncSession, token: str) -> dict:
    """Rotate the refresh token, with reuse detection.

    Every successful refresh mints a *new* refresh token and revokes the one presented.
    If a token that was already rotated away comes back, that means two parties hold the
    same token — a theft. The only safe response is to revoke the entire rotation family,
    forcing a real login. (ADR-0023.)
    """
    try:
        payload = decode_token(token)
    except JWTError:
        raise InvalidToken("Refresh token is invalid or expired.")

    if payload.get("type") != "refresh":
        raise InvalidToken("Token is not a refresh token.")

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
    )
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise InvalidToken("Refresh token is invalid or has been revoked.")

    if db_token.revoked or db_token.replaced_by_id is not None:
        # Reuse of a spent token. Nuke the family and make them log in again.
        await _revoke_family(db, db_token.family_id)
        await db.commit()
        raise InvalidToken("Refresh token reuse detected. All sessions have been revoked.")

    if db_token.expires_at <= utcnow():
        db_token.revoked = True
        await db.commit()
        raise InvalidToken("Refresh token is invalid or expired.")

    user = await db.get(User, db_token.user_id)
    if user is None or user.deleted_at is not None:
        raise InvalidToken("Refresh token is invalid or has been revoked.")
    if user.is_banned:
        await _revoke_family(db, db_token.family_id)
        await db.commit()
        raise AccountBanned(user.banned_reason or "This account has been suspended.")

    new_refresh, new_row = await _issue_refresh_token(db, user.id, family_id=db_token.family_id)
    db_token.revoked = True
    db_token.replaced_by_id = new_row.id

    new_access = create_access_token(str(user.id))
    user.last_seen_at = utcnow()
    await db.commit()

    return {"access_token": new_access, "refresh_token": new_refresh}


async def logout_user(db: AsyncSession, token: str) -> None:
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
    )
    db_token = result.scalar_one_or_none()
    if db_token is None:
        raise InvalidToken("Refresh token not found.")

    # Log out the whole rotation chain, not just the token that happened to be presented.
    await _revoke_family(db, db_token.family_id)
    await db.commit()


async def updateprofile(db: AsyncSession, user_id, new_name: str, new_email: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")

    new_email = new_email.strip().lower()
    if new_email != user.email:
        email_check = await db.execute(select(User).where(User.email == new_email))
        if email_check.scalar_one_or_none():
            raise EmailAlreadyExists(f"Email {new_email} is already registered.")

    user.name = new_name
    user.email = new_email
    await db.commit()
    await db.refresh(user)
    return user


async def updatepassword(
    db: AsyncSession, user_id, current_password: str, new_password: str
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")

    is_valid = await asyncio.to_thread(verify_password, current_password, user.password_hash)
    if not is_valid:
        raise InvalidCredentials("Current password is incorrect.")

    user.password_hash = await asyncio.to_thread(hash_password, new_password)
    # Changing a password must end every other session, or the change protects nothing.
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True)
    )
    await db.commit()
    await db.refresh(user)
    return user


async def deleteuser(db: AsyncSession, user_id) -> None:
    """Anonymise the account rather than DELETE the row.

    A hard delete would either fail (duels and submissions reference `users` with the
    default RESTRICT) or cascade away matches that are also the *opponent's* history.
    Anonymising removes every piece of personal data while leaving the ladder intact.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise InvalidCredentials("User not found.")

    user.email = f"deleted-{user.id}@deleted.invalid"
    user.name = "Deleted user"
    user.password_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(32))
    user.deleted_at = utcnow()
    user.plan = "free"
    user.plan_expires_at = None

    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True)
    )
    await db.commit()
