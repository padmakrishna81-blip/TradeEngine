"""Repository for Position model."""
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import Position
from state_quant_engine.repositories.base_repository import BaseRepository


class PositionRepository(BaseRepository[Position]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Position)

    def get_open_positions(self, version_id: int = 1) -> List[Position]:
        return (
            self._session.query(Position)
            .filter(Position.status == "OPEN", Position.version_id == version_id)
            .all()
        )

    def get_by_symbol(self, symbol: str, version_id: int = 1) -> List[Position]:
        return (
            self._session.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.status == "OPEN",
                Position.version_id == version_id,
            )
            .order_by(Position.cycle, Position.chunk_no)
            .all()
        )

    def get_by_symbol_cycle_chunk(
        self, symbol: str, cycle: int, chunk_no: int, version_id: int = 1
    ) -> Optional[Position]:
        return (
            self._session.query(Position)
            .filter(
                Position.symbol == symbol,
                Position.cycle == cycle,
                Position.chunk_no == chunk_no,
                Position.version_id == version_id,
            )
            .first()
        )

    def get_max_cycle(self, symbol: str, version_id: int = 1) -> int:
        result = (
            self._session.query(Position)
            .filter(Position.symbol == symbol, Position.version_id == version_id)
            .order_by(Position.cycle.desc())
            .first()
        )
        return result.cycle if result else 0
