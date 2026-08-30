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