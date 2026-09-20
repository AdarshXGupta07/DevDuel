import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings

ALGORITHM = "HS256"

# Kept as module constants for backwards compatibility; the real values come from settings.
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes
REFRESH_TOKEN_EXPIRE_DAYS = settings.refresh_token_expire_days


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    expire = utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": utcnow(),
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": utcnow(),
        "type": "refresh",
        # A unique id per issued token. Without it, two refresh tokens minted for the same
        # user in the same second are byte-identical — which collides with the UNIQUE
        # constraint on token_hash and makes rotation chains ambiguous.
        "jti": str(uuid.uuid4()),
        "nonce": secrets.token_urlsafe(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def hash_token(token: str) -> str:
    """Hash a refresh token for storage.

    Refresh tokens are long, high-entropy and already signed, so a fast hash is the right
    tool here — unlike passwords, there is no low-entropy guess space to slow an attacker
    down over. What this buys: a stolen database dump contains no usable sessions.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry(token: str) -> datetime:
    """The `exp` claim as an aware datetime, for storing alongside the hash."""
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"verify_exp": False},
    )
    return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
