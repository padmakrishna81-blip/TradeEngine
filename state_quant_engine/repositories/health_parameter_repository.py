"""Repository for HealthParameter model."""
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import HealthParameter
from state_quant_engine.repositories.base_repository import BaseRepository

SCOPE_ENTRY = "entry"
SCOPE_HOLD  = "hold"
SCOPE_BOTH  = "both"


class HealthParameterRepository(BaseRepository[HealthParameter]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, HealthParameter)

    def get_by_name(self, name: str, scope: str = SCOPE_ENTRY) -> Optional[HealthParameter]:
        return (
            self._session.query(HealthParameter)
            .filter(HealthParameter.parameter_name == name,
                    HealthParameter.scope == scope)
            .first()
        )

    def get_by_scope(self, scope: str) -> List[HealthParameter]:
        """Return all params matching scope exactly."""
        return (
            self._session.query(HealthParameter)
            .filter(HealthParameter.scope == scope)
            .all()
        )

    def get_enabled(self, scope: Optional[str] = None) -> List[HealthParameter]:
        """Return enabled params; if scope given, filter to that scope."""
        q = self._session.query(HealthParameter).filter(HealthParameter.enabled == True)
        if scope:
            q = q.filter(HealthParameter.scope == scope)
        return q.all()

    def get_enabled_for_entry(self) -> List[HealthParameter]:
        return self.get_enabled(SCOPE_ENTRY)

    def get_enabled_for_hold(self) -> List[HealthParameter]:
        return self.get_enabled(SCOPE_HOLD)

    def upsert(self, name: str, weight: float, enabled: bool, threshold: float,
               description: str, scope: str = SCOPE_ENTRY) -> HealthParameter:
        existing = self.get_by_name(name, scope)
        if existing:
            existing.weight      = weight
            existing.enabled     = enabled
            existing.threshold   = threshold
            existing.description = description
            self._session.commit()
            return existing
        hp = HealthParameter(
            parameter_name=name, weight=weight, enabled=enabled,
            threshold=threshold, description=description, scope=scope,
        )
        return self.add(hp)
