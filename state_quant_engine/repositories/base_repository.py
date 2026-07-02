"""Base repository with common CRUD operations."""
from __future__ import annotations
from typing import Generic, TypeVar, Type, List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic repository providing CRUD for any ORM model."""

    def __init__(self, session: Session, model: Type[T]) -> None:
        self._session = session
        self._model = model

    def get_by_id(self, record_id: int) -> Optional[T]:
        return self._session.get(self._model, record_id)

    def get_all(self) -> List[T]:
        return self._session.query(self._model).all()

    def add(self, entity: T) -> T:
        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        self._session.commit()
        self._session.refresh(entity)
        return entity

    def delete(self, entity: T) -> None:
        self._session.delete(entity)
        self._session.commit()

    def bulk_add(self, entities: List[T]) -> None:
        self._session.add_all(entities)
        self._session.commit()
