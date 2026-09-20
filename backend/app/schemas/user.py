import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserAccept(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    rating: int
    plan: str
    ranked_matches_played: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    """What an opponent is allowed to see. Deliberately no email."""

    id: uuid.UUID
    name: str
    rating: int

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserTokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str


class UserUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    email: EmailStr


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
