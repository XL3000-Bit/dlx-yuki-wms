from typing import Any, Generic, TypeVar
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, model: type[ModelT]): self.model = model
    def list(self, db: Session, offset: int = 0, limit: int = 100) -> list[ModelT]:
        return list(db.scalars(select(self.model).offset(offset).limit(limit)).all())
    def get(self, db: Session, object_id: int) -> ModelT | None: return db.get(self.model, object_id)
    def create(self, db: Session, values: dict[str, Any]) -> ModelT:
        obj = self.model(**values); db.add(obj); db.commit(); db.refresh(obj); return obj
    def delete(self, db: Session, obj: ModelT) -> None: db.delete(obj); db.commit()
