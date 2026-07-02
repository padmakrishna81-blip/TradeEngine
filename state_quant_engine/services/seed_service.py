"""Seed service - populates DB with defaults from YAML config."""
from __future__ import annotations
from typing import Any
from loguru import logger
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
from state_quant_engine.repositories.watchlist_repository import WatchlistRepository
from state_quant_engine.repositories.scan_strategy_repository import StrategyRepository
from state_quant_engine.repositories.version_repository import VersionRepository
from state_quant_engine.repositories.watchlist_group_repository import WatchlistGroupRepository


def seed_defaults(settings: Any) -> None:
    """Seed database with defaults if empty."""
    session = get_session()
    try:
        _seed_live_version(session)
        _seed_watchlist_groups(session)
        _seed_health_parameters(session, settings)
        _seed_watchlist(session, settings)
        _seed_strategies(session, settings)
        _seed_admin_user(session)
        _load_symbol_allocations(session, settings)
    finally:
        session.close()


def _seed_live_version(session) -> None:
    repo = VersionRepository(session)
    repo.seed_live()


def _seed_admin_user(session) -> None:
    from state_quant_engine.repositories.user_repository import UserRepository
    UserRepository(session).seed_admin()


def _seed_watchlist_groups(session) -> None:
    repo = WatchlistGroupRepository(session)
    repo.seed_default()


def _seed_health_parameters(session, settings) -> None:
    repo = HealthParameterRepository(session)
    existing = repo.get_all()
    if existing:
        return
    for param in settings.health_parameters:
        repo.upsert(
            name=param["name"],
            weight=param["weight"],
            enabled=param["enabled"],
            threshold=param.get("threshold", 0),
            description=param.get("description", ""),
        )
    logger.info("Seeded health parameters")


def _seed_watchlist(session, settings) -> None:
    repo       = WatchlistRepository(session)
    grp_repo   = WatchlistGroupRepository(session)
    existing   = repo.get_all()
    if existing:
        # Ensure existing items have a group
        default = grp_repo.get_default() or grp_repo.seed_default()
        for item in existing:
            if item.watchlist_group_id is None:
                item.watchlist_group_id = default.id
        session.commit()
        return
    default = grp_repo.get_default() or grp_repo.seed_default()
    wl = settings.default_watchlist
    for item in wl.get("etfs", []):
        repo.upsert(
            symbol=item["symbol"],
            name=item.get("name", item["symbol"]),
            exchange=item.get("exchange", "NSE"),
            asset_type="ETF",
            priority=1,
            group_id=default.id,
        )
    for item in wl.get("stocks", []):
        repo.upsert(
            symbol=item["symbol"],
            name=item.get("name", item["symbol"]),
            exchange=item.get("exchange", "NSE"),
            asset_type="STOCK",
            priority=2,
            group_id=default.id,
        )
    logger.info("Seeded watchlist")


def _seed_strategies(session, settings) -> None:
    repo = StrategyRepository(session)
    existing = repo.get_all()
    if existing:
        return
    for i, strat in enumerate(settings.strategies):
        s = repo.upsert(
            name=strat["name"],
            description=strat.get("description", ""),
            parameters=strat.get("parameters", {}),
            exit_style=strat.get("exit_style", "trailing"),
            use_case=strat.get("use_case", ""),
        )
        if i == 0:
            repo.set_active(s.id)
    logger.info("Seeded strategies")


def _load_symbol_allocations(session, settings) -> None:
    """Load persisted symbol allocations into settings.symbol_allocations."""
    try:
        from state_quant_engine.repositories.symbol_allocation_repository import SymbolAllocationRepository
        repo = SymbolAllocationRepository(session)
        settings.symbol_allocations = repo.get_all_as_dict()
    except Exception as e:
        logger.warning(f"Could not load symbol allocations: {e}")
