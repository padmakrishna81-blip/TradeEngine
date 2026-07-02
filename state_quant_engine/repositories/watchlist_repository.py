"""Repository for WatchlistItem model."""
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import WatchlistItem
from state_quant_engine.repositories.base_repository import BaseRepository


class WatchlistRepository(BaseRepository[WatchlistItem]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, WatchlistItem)

    def get_by_symbol(self, symbol: str) -> Optional[WatchlistItem]:
        return (
            self._session.query(WatchlistItem)
            .filter(WatchlistItem.symbol == symbol)
            .first()
        )

    def get_by_symbol_and_group(self, symbol: str, group_id: int) -> Optional[WatchlistItem]:
        return (
            self._session.query(WatchlistItem)
            .filter(WatchlistItem.symbol == symbol,
                    WatchlistItem.watchlist_group_id == group_id)
            .first()
        )

    def get_enabled(self, group_id: Optional[int] = None) -> List[WatchlistItem]:
        """Return enabled items — optionally filtered to a specific group."""
        q = self._session.query(WatchlistItem).filter(WatchlistItem.enabled == True)
        if group_id is not None:
            q = q.filter(WatchlistItem.watchlist_group_id == group_id)
        return q.order_by(WatchlistItem.priority, WatchlistItem.symbol).all()

    def get_by_group(self, group_id: int) -> List[WatchlistItem]:
        """All items (enabled or not) in a group."""
        return (
            self._session.query(WatchlistItem)
            .filter(WatchlistItem.watchlist_group_id == group_id)
            .order_by(WatchlistItem.priority, WatchlistItem.symbol)
            .all()
        )

    def get_by_type(self, asset_type: str) -> List[WatchlistItem]:
        return (
            self._session.query(WatchlistItem)
            .filter(WatchlistItem.asset_type == asset_type)
            .order_by(WatchlistItem.priority, WatchlistItem.symbol)
            .all()
        )

    def upsert(self, symbol: str, name: str, exchange: str, asset_type: str,
               priority: int = 5, group_id: Optional[int] = None) -> WatchlistItem:
        existing = (
            self.get_by_symbol_and_group(symbol, group_id)
            if group_id else self.get_by_symbol(symbol)
        )
        if existing:
            existing.name      = name
            existing.exchange  = exchange
            existing.asset_type = asset_type
            existing.priority  = priority
            if group_id and existing.watchlist_group_id != group_id:
                existing.watchlist_group_id = group_id
            self._session.commit()
            return existing
        item = WatchlistItem(
            symbol=symbol, name=name, exchange=exchange,
            asset_type=asset_type, priority=priority,
            watchlist_group_id=group_id,
        )
        return self.add(item)

    def copy_to_group(self, item: WatchlistItem, target_group_id: int) -> WatchlistItem:
        """Copy a symbol to another group (for cloning watchlists)."""
        existing = self.get_by_symbol_and_group(item.symbol, target_group_id)
        if existing:
            return existing
        new_item = WatchlistItem(
            symbol=item.symbol, name=item.name, exchange=item.exchange,
            asset_type=item.asset_type, priority=item.priority,
            enabled=item.enabled, watchlist_group_id=target_group_id,
        )
        return self.add(new_item)
