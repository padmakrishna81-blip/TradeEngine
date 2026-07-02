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
    from state_quant_engine.repositories.health_parameter_repository import (
        HealthParameterRepository, SCOPE_ENTRY, SCOPE_HOLD,
    )
    repo = HealthParameterRepository(session)

    # Only seed if neither entry nor hold rows exist yet
    if repo.get_enabled_for_entry() or repo.get_enabled_for_hold():
        # migrate old rows (no scope column) to entry scope
        old_unscopeds = [p for p in repo.get_all() if p.scope not in (SCOPE_ENTRY, SCOPE_HOLD)]
        for p in old_unscopeds:
            p.scope = SCOPE_ENTRY
        if old_unscopeds:
            session.commit()
        return

    # ── Entry Health parameters (6 params, total weight 100) ─────────────
    entry_params = [
        {"name": "200 DMA",           "weight": 25, "threshold": 0,   "description": "Price vs 200-day EMA (entry rules)"},
        {"name": "Drawdown",          "weight": 20, "threshold": 0,   "description": "Bell-curve drawdown from 60-day high"},
        {"name": "Relative Strength", "weight": 20, "threshold": 0,   "description": "Stock 20-day return vs Nifty"},
        {"name": "Volume Spike",      "weight": 10, "threshold": 1.5, "description": "Volume ratio vs 20-day average"},
        {"name": "RSI",               "weight": 15, "threshold": 50,  "description": "RSI(14) — entry zone 48-60"},
        {"name": "MACD",              "weight": 10, "threshold": 0,   "description": "MACD line vs signal + histogram slope"},
    ]
    for p in entry_params:
        repo.upsert(name=p["name"], weight=p["weight"], enabled=True,
                    threshold=p["threshold"], description=p["description"],
                    scope=SCOPE_ENTRY)

    # ── Hold Health parameters (7 params, total weight 100+20 = normalized) ─
    # Profit % is an extra parameter for hold — contributes to exit scoring
    hold_params = [
        {"name": "200 DMA",           "weight": 25, "threshold": 0,    "description": "Price vs 200-day EMA (hold rules — more forgiving)"},
        {"name": "Drawdown",          "weight": 20, "threshold": 0,    "description": "Drawdown from 60-day high (hold rules)"},
        {"name": "Relative Strength", "weight": 20, "threshold": 0,    "description": "Stock 20-day return vs Nifty (hold rules)"},
        {"name": "Volume Spike",      "weight": 10, "threshold": 1.0,  "description": "Volume ratio — lower threshold for holding"},
        {"name": "RSI",               "weight": 15, "threshold": 45,   "description": "RSI(14) — hold zone 45-70"},
        {"name": "MACD",              "weight": 10, "threshold": 0,    "description": "MACD state for holding"},
        {"name": "Profit %",          "weight": 20, "threshold": 10.0, "description": "MTM profit contribution — threshold = profit % that triggers exit review"},
    ]
    for p in hold_params:
        repo.upsert(name=p["name"], weight=p["weight"], enabled=True,
                    threshold=p["threshold"], description=p["description"],
                    scope=SCOPE_HOLD)

    logger.info("Seeded entry and hold health parameters")


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
