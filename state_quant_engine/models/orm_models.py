"""ORM models for STATE Quant Engine."""
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, Date, DateTime,
    Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from state_quant_engine.models.base import Base


class AppUser(Base):
    """Application users for login."""
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[date] = mapped_column(Date, default=date.today)

    def __repr__(self) -> str:
        return f"<AppUser {self.username}>"


class SymbolAllocation(Base):
    """Per-symbol capital allocation percentage within ETF or Stock pool."""
    __tablename__ = "symbol_allocation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), default="ETF")
    allocation_pct: Mapped[float] = mapped_column(Float, default=0.0)

    def __repr__(self) -> str:
        return f"<SymbolAllocation {self.symbol} {self.allocation_pct}%>"


class TradingVersion(Base):
    """Paper-trade / sandbox versions. One row is always the live version."""
    __tablename__ = "trading_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[date] = mapped_column(Date, default=date.today)

    def __repr__(self) -> str:
        tag = " [LIVE]" if self.is_live else ""
        return f"<TradingVersion {self.name}{tag}>"


class HealthParameter(Base):
    """Configurable health scoring parameters."""
    __tablename__ = "health_parameter"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parameter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=10.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(10), default="entry")
    # scope values: "entry" (scanner), "hold" (portfolio), "both"

    __table_args__ = (
        __import__("sqlalchemy").UniqueConstraint("parameter_name", "scope",
                                                  name="uq_health_param_name_scope"),
    )

    def __repr__(self) -> str:
        return f"<HealthParameter {self.parameter_name} scope={self.scope} w={self.weight}>"


class AssetType(Base):
    """Asset type reference table."""
    __tablename__ = "asset_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    watchlist_items: Mapped[list["WatchlistItem"]] = relationship(back_populates="asset_type_rel")


class WatchlistGroup(Base):
    """Named watchlist groups — users can create multiple watchlists."""
    __tablename__ = "watchlist_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["WatchlistItem"]] = relationship(back_populates="group", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<WatchlistGroup {self.name}>"


class WatchlistItem(Base):
    """Watchlist symbols to track."""
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, default="STOCK")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    watchlist_group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("watchlist_group.id"), nullable=True)
    group: Mapped[Optional["WatchlistGroup"]] = relationship(back_populates="items")
    asset_type_id: Mapped[Optional[int]] = mapped_column(ForeignKey("asset_type.id"), nullable=True)
    asset_type_rel: Mapped[Optional["AssetType"]] = relationship(back_populates="watchlist_items")

    def __repr__(self) -> str:
        return f"<WatchlistItem {self.symbol}>"


class Portfolio(Base):
    """Portfolio capital allocation per symbol."""
    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    capital: Mapped[float] = mapped_column(Float, default=0.0)
    allocated: Mapped[float] = mapped_column(Float, default=0.0)
    available: Mapped[float] = mapped_column(Float, default=0.0)
    asset_type: Mapped[str] = mapped_column(String(20), default="STOCK")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class Position(Base):
    """Individual trade positions with chunk tracking."""
    __tablename__ = "position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    cycle: Mapped[int] = mapped_column(Integer, default=1)
    chunk_no: Mapped[int] = mapped_column(Integer, default=1)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)
    buy_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    highest_price: Mapped[float] = mapped_column(Float, default=0.0)
    highest_profit: Mapped[float] = mapped_column(Float, default=0.0)
    current_profit: Mapped[float] = mapped_column(Float, default=0.0)
    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    version_id: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("symbol", "cycle", "chunk_no", "version_id", name="uq_position_cycle_chunk_ver"),
    )

    def __repr__(self) -> str:
        return f"<Position {self.symbol} cy={self.cycle} ch={self.chunk_no} v={self.version_id}>"


class TradeLog(Base):
    """Complete log of all trade actions."""
    __tablename__ = "trade_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    remarks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version_id: Mapped[int] = mapped_column(Integer, default=1)


class ScanHistory(Base):
    """Historical scan results."""
    __tablename__ = "scan_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String(20), default="WATCH")
    version_id: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("date", "symbol", "version_id", name="uq_scan_date_symbol_ver"),
    )


class Strategy(Base):
    """Named strategy profiles for the Strategy Lab."""
    __tablename__ = "strategy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exit_style: Mapped[str] = mapped_column(String(50), default="trailing")
    use_case: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    drawdown_days: Mapped[int] = mapped_column(Integer, default=52)

    def __repr__(self) -> str:
        return f"<Strategy {self.name}>"
