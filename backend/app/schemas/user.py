import uuid
from datetime import datetime
from pydantic import BaseModel, Field

class UserAccept(BaseModel):
    name: str
    email: str
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    rating: int = Field(default=1200)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
    
class UserLogin(BaseModel):
    email: str
    password: str

class UserTokens(BaseModel):
    access_token: str
    refresh_token: str

class RefreshRequest(BaseModel):
    refresh_token: str

class AccessTokenResponse(BaseModel):
    access_token: str

class UserUpdate(BaseModel):
    name: str
    email: str

class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str