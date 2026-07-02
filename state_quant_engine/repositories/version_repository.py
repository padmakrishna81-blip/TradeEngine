"""Repository for TradingVersion model."""
from __future__ import annotations
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import TradingVersion
from state_quant_engine.repositories.base_repository import BaseRepository


class VersionRepository(BaseRepository[TradingVersion]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TradingVersion)

    def get_live(self) -> Optional[TradingVersion]:
        return self._session.query(TradingVersion).filter(TradingVersion.is_live == True).first()

    def get_by_name(self, name: str) -> Optional[TradingVersion]:
        return self._session.query(TradingVersion).filter(TradingVersion.name == name).first()

    def get_all_ordered(self) -> List[TradingVersion]:
        """Return versions with Live first, then paper versions by name."""
        return (
            self._session.query(TradingVersion)
            .order_by(TradingVersion.is_live.desc(), TradingVersion.name)
            .all()
        )

    def create_paper(self, name: str, description: str = "") -> TradingVersion:
        v = TradingVersion(
            name=name,
            description=description,
            is_live=False,
            created_at=date.today(),
        )
        return self.add(v)

    def seed_live(self) -> TradingVersion:
        """Ensure the Live version row exists (id=1)."""
        live = self.get_live()
        if live:
            return live
        v = TradingVersion(
            name="Live",
            description="Actual / production trading",
            is_live=True,
            created_at=date.today(),
        )
        self._session.add(v)
        self._session.flush()   # get the id without full commit
        self._session.commit()
        return v
