"""Repository for WatchlistGroup and updated WatchlistItem queries."""
from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import WatchlistGroup, WatchlistItem
from state_quant_engine.repositories.base_repository import BaseRepository


class WatchlistGroupRepository(BaseRepository[WatchlistGroup]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, WatchlistGroup)

    def get_by_name(self, name: str) -> Optional[WatchlistGroup]:
        return self._session.query(WatchlistGroup).filter(
            WatchlistGroup.name == name
        ).first()

    def get_default(self) -> Optional[WatchlistGroup]:
        return self._session.query(WatchlistGroup).filter(
            WatchlistGroup.is_default == True
        ).first()

    def get_all_ordered(self) -> List[WatchlistGroup]:
        return (
            self._session.query(WatchlistGroup)
            .order_by(WatchlistGroup.is_default.desc(), WatchlistGroup.name)
            .all()
        )

    def create_group(self, name: str, description: str = "") -> WatchlistGroup:
        g = WatchlistGroup(name=name, description=description, is_default=False)
        return self.add(g)

    def seed_default(self) -> WatchlistGroup:
        default = self.get_default()
        if default:
            return default
        g = WatchlistGroup(name="Default", description="Default watchlist", is_default=True)
        self._session.add(g)
        self._session.commit()
        return g

    def symbol_count(self, group_id: int) -> int:
        return self._session.query(WatchlistItem).filter(
            WatchlistItem.watchlist_group_id == group_id
        ).count()
