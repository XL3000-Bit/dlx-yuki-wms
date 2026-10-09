from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Timestamped(ORMModel):
    id: int
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    message: str
