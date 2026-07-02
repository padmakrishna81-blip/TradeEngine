"""Repository for HealthParameter model."""
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import HealthParameter
from state_quant_engine.repositories.base_repository import BaseRepository


class HealthParameterRepository(BaseRepository[HealthParameter]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, HealthParameter)

    def get_by_name(self, name: str) -> Optional[HealthParameter]:
        return (
            self._session.query(HealthParameter)
            .filter(HealthParameter.parameter_name == name)
            .first()
        )

    def get_enabled(self) -> List[HealthParameter]:
        return (
            self._session.query(HealthParameter)
            .filter(HealthParameter.enabled == True)
            .all()
        )

    def upsert(self, name: str, weight: float, enabled: bool, threshold: float, description: str) -> HealthParameter:
        existing = self.get_by_name(name)
        if existing:
            existing.weight = weight
            existing.enabled = enabled
            existing.threshold = threshold
            existing.description = description
            self._session.commit()
            return existing
        hp = HealthParameter(
            parameter_name=name,
            weight=weight,
            enabled=enabled,
            threshold=threshold,
            description=description,
        )
        return self.add(hp)
