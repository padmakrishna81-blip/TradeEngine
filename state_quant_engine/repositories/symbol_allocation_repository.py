"""Repository for SymbolAllocation model."""
from __future__ import annotations
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import SymbolAllocation
from state_quant_engine.repositories.base_repository import BaseRepository


class SymbolAllocationRepository(BaseRepository[SymbolAllocation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, SymbolAllocation)

    def get_by_symbol(self, symbol: str) -> Optional[SymbolAllocation]:
        return self._session.query(SymbolAllocation).filter(
            SymbolAllocation.symbol == symbol
        ).first()

    def get_by_type(self, asset_type: str) -> List[SymbolAllocation]:
        return (
            self._session.query(SymbolAllocation)
            .filter(SymbolAllocation.asset_type == asset_type)
            .order_by(SymbolAllocation.symbol)
            .all()
        )

    def get_all_as_dict(self) -> Dict[str, float]:
        """Return {symbol: allocation_pct} for all symbols."""
        rows = self.get_all()
        return {r.symbol: r.allocation_pct for r in rows}

    def upsert(self, symbol: str, asset_type: str, allocation_pct: float) -> SymbolAllocation:
        existing = self.get_by_symbol(symbol)
        if existing:
            existing.asset_type    = asset_type
            existing.allocation_pct = allocation_pct
            self._session.commit()
            return existing
        obj = SymbolAllocation(symbol=symbol, asset_type=asset_type,
                               allocation_pct=allocation_pct)
        return self.add(obj)

    def get_allocation_for_symbol(self, symbol: str, total_capital: float) -> float:
        """Return the ₹ amount allocated to this symbol (0 if not configured)."""
        row = self.get_by_symbol(symbol)
        if row and row.allocation_pct > 0:
            return total_capital * row.allocation_pct / 100
        return 0.0
