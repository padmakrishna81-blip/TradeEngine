"""Repository for TradeLog model."""
from __future__ import annotations
from datetime import date, datetime
from typing import List
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import TradeLog
from state_quant_engine.repositories.base_repository import BaseRepository


class TradeLogRepository(BaseRepository[TradeLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TradeLog)

    def get_by_symbol(self, symbol: str, version_id: int = 1) -> List[TradeLog]:
        return (
            self._session.query(TradeLog)
            .filter(TradeLog.symbol == symbol, TradeLog.version_id == version_id)
            .order_by(TradeLog.date.desc())
            .all()
        )

    def get_by_date_range(self, start: date, end: date, version_id: int = 1) -> List[TradeLog]:
        return (
            self._session.query(TradeLog)
            .filter(
                TradeLog.date >= datetime.combine(start, datetime.min.time()),
                TradeLog.date <= datetime.combine(end, datetime.max.time()),
                TradeLog.version_id == version_id,
            )
            .order_by(TradeLog.date.desc())
            .all()
        )

    def get_all_versions(self, start: date, end: date) -> List[TradeLog]:
        """Fetch all trade logs across all versions for cross-version reports."""
        return (
            self._session.query(TradeLog)
            .filter(
                TradeLog.date >= datetime.combine(start, datetime.min.time()),
                TradeLog.date <= datetime.combine(end, datetime.max.time()),
            )
            .order_by(TradeLog.date.desc())
            .all()
        )

    def log_trade(
        self, symbol: str, action: str, price: float, quantity: float,
        remarks: str = "", version_id: int = 1,
    ) -> TradeLog:
        entry = TradeLog(
            symbol=symbol,
            action=action,
            price=price,
            quantity=quantity,
            remarks=remarks,
            version_id=version_id,
        )
        return self.add(entry)

    def count_by_version(self, version_id: int) -> int:
        return self._session.query(TradeLog).filter(TradeLog.version_id == version_id).count()
