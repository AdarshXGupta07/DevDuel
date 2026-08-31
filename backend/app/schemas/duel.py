import uuid
from datetime import datetime
from pydantic import BaseModel


class DuelResponse(BaseModel):
    id: uuid.UUID
    player1_id: uuid.UUID
    player2_id: uuid.UUID
    problem_id: uuid.UUID
    status: str
    winner_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
