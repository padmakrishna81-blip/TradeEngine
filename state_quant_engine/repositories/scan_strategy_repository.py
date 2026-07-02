"""Repository for ScanHistory and Strategy models."""
from __future__ import annotations
from datetime import date
from typing import List, Optional
import json
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import ScanHistory, Strategy
from state_quant_engine.repositories.base_repository import BaseRepository


class ScanHistoryRepository(BaseRepository[ScanHistory]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ScanHistory)

    def upsert(self, scan_date: date, symbol: str, score: float, recommendation: str,
               version_id: int = 1) -> ScanHistory:
        existing = (
            self._session.query(ScanHistory)
            .filter(
                ScanHistory.date == scan_date,
                ScanHistory.symbol == symbol,
                ScanHistory.version_id == version_id,
            )
            .first()
        )
        if existing:
            existing.score = score
            existing.recommendation = recommendation
            self._session.commit()
            return existing
        entry = ScanHistory(
            date=scan_date, symbol=symbol, score=score,
            recommendation=recommendation, version_id=version_id,
        )
        return self.add(entry)

    def get_latest_for_symbol(self, symbol: str, version_id: int = 1) -> Optional[ScanHistory]:
        return (
            self._session.query(ScanHistory)
            .filter(ScanHistory.symbol == symbol, ScanHistory.version_id == version_id)
            .order_by(ScanHistory.date.desc())
            .first()
        )

    def get_by_version(self, version_id: int) -> List[ScanHistory]:
        return (
            self._session.query(ScanHistory)
            .filter(ScanHistory.version_id == version_id)
            .order_by(ScanHistory.date.desc())
            .all()
        )


class StrategyRepository(BaseRepository[Strategy]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Strategy)

    def get_active(self) -> Optional[Strategy]:
        return (
            self._session.query(Strategy)
            .filter(Strategy.is_active == True)
            .first()
        )

    def set_active(self, strategy_id: int) -> None:
        self._session.query(Strategy).update({Strategy.is_active: False})
        strat = self._session.get(Strategy, strategy_id)
        if strat:
            strat.is_active = True
        self._session.commit()

    def get_by_name(self, name: str) -> Optional[Strategy]:
        return self._session.query(Strategy).filter(Strategy.name == name).first()

    def upsert(self, name: str, description: str, parameters: dict, exit_style: str, use_case: str, drawdown_days: int = 52) -> Strategy:
        existing = self.get_by_name(name)
        params_json = json.dumps(parameters)
        if existing:
            existing.description = description
            existing.parameters = params_json
            existing.exit_style = exit_style
            existing.use_case = use_case
            existing.drawdown_days = drawdown_days
            self._session.commit()
            return existing
        strat = Strategy(
            name=name,
            description=description,
            parameters=params_json,
            exit_style=exit_style,
            use_case=use_case,
            drawdown_days=drawdown_days,
        )
        return self.add(strat)
