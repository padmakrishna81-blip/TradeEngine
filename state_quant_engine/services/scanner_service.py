"""Scanner service - orchestrates data fetch, indicators, and scoring."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import date
import pandas as pd
from loguru import logger
from state_quant_engine.engine.indicators.data_fetcher import fetch_ohlcv, fetch_current_price
from state_quant_engine.engine.indicators.technical import compute_indicators, compute_market_breadth, IndicatorResult
from state_quant_engine.engine.health_score_engine import (
    EntryHealthEngine, HoldHealthEngine, HealthScoreEngine, HealthScoreResult,
    load_profile_engine,
)
from state_quant_engine.engine.health_score_engine_market import MarketHealthEngine
from state_quant_engine.engine.trade_engine import EntryEngine, HoldEngine, ExitEngine, ChunkEngine, TradeSignal
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
from state_quant_engine.repositories.watchlist_repository import WatchlistRepository
from state_quant_engine.repositories.position_repository import PositionRepository
from state_quant_engine.repositories.scan_strategy_repository import ScanHistoryRepository


@dataclass
class ScanResult:
    rank: int
    symbol: str
    name: str
    asset_type: str
    price: float
    health_score: float
    max_score: float
    score_pct: float
    recommendation: str
    reasons: List[str]
    component_scores: Dict[str, float]
    indicator: Optional[IndicatorResult] = None
    current_profit: float = 0.0
    has_position: bool = False
    chunks_held: int = 0
    next_buy_price: Optional[float] = None
    error: Optional[str] = None
    trend: str = ""
    trend_reason: str = ""
    risk: str = ""
    risk_reason: str = ""
    market_score: float = 0.0
    deploy_pct: float = 100.0
    deploy_label: str = ""
    change_pct: float = 0.0    # day % change vs previous session close
    prev_close: float = 0.0    # previous session close price


class ScannerService:
    """Runs full scan pipeline for all enabled watchlist symbols."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._benchmark_df: Optional[pd.DataFrame] = None
        self._vix_df: Optional[pd.DataFrame] = None

    def _get_stock_parameters(self) -> List[Dict]:
        """Return ENTRY health parameters from DB (scope='entry')."""
        session = get_session()
        try:
            from state_quant_engine.repositories.health_parameter_repository import SCOPE_ENTRY
            repo   = HealthParameterRepository(session)
            params = repo.get_enabled_for_entry()
            if params:
                return [
                    {"parameter_name": p.parameter_name, "weight": p.weight,
                     "enabled": p.enabled, "threshold": p.threshold}
                    for p in params
                ]
        finally:
            session.close()
        return (self.settings.stock_health_parameters or self.settings.health_parameters)

    def _load_auxiliary(self) -> None:
        """Load benchmark (NIFTY) and VIX data."""
        try:
            self._benchmark_df = fetch_ohlcv("^NSEI", period=self.settings.data.download_period)
        except Exception:
            self._benchmark_df = pd.DataFrame()
        try:
            self._vix_df = fetch_ohlcv("^INDIAVIX", period="1mo")
        except Exception:
            self._vix_df = pd.DataFrame()

    def _compute_market_health(self, market_breadth: float) -> tuple:
        """Compute market health score and return (score_pct, deploy_pct, deploy_label, reasons)."""
        from state_quant_engine.engine.indicators.technical import compute_indicators, IndicatorResult
        if self._benchmark_df is None or self._benchmark_df.empty:
            return 0.0, 100.0, "No market data", []

        nifty_ind = compute_indicators(self._benchmark_df, "^NSEI",
                                        drawdown_days=self.settings.data.drawdown_days)
        # Inject market-wide metrics into the NIFTY indicator result
        nifty_ind.breadth = market_breadth
        if self._vix_df is not None and not self._vix_df.empty:
            nifty_ind.vix = float(self._vix_df["close"].iloc[-1])

        mh_params = self.settings.market_health_parameters
        deploy_tiers = self.settings.market_deploy_tiers
        mh_engine = MarketHealthEngine(
            parameters=mh_params or None,
            deploy_tiers=deploy_tiers or None,
        )
        mh = mh_engine.compute(nifty_ind)
        return mh.score_pct, mh.deploy_pct, mh.deploy_label, mh.reasons, mh.component_scores

    def run(self, symbols: Optional[List[str]] = None, strategy_params: Optional[List[Dict]] = None,
            drawdown_days: Optional[int] = None, version_id: int = 1,
            watchlist_group_id: Optional[int] = None) -> List[ScanResult]:
        """
        Scanner = fresh entries only.
        Symbols that already have an OPEN position for this version are excluded —
        those belong to the Portfolio workflow.
        Returns only BUY / WAIT recommendations.
        Profile-driven: loads stock_entry or etf_entry profile per symbol.
        """
        self._load_auxiliary()
        dd_days = drawdown_days if drawdown_days is not None else self.settings.data.drawdown_days

        chunk_engine = ChunkEngine(self.settings)

        session = get_session()
        try:
            wl_repo  = WatchlistRepository(session)
            pos_repo = PositionRepository(session)

            if symbols:
                watchlist = [w for w in wl_repo.get_enabled(group_id=watchlist_group_id)
                             if w.symbol in symbols]
            else:
                watchlist = wl_repo.get_enabled(group_id=watchlist_group_id)

            # SCANNER ONLY handles symbols NOT currently in portfolio for this version
            open_symbols = {p.symbol for p in pos_repo.get_open_positions(version_id=version_id)}
            watchlist = [w for w in watchlist if w.symbol not in open_symbols]

            # Pre-load one engine per asset type using profiles
            _engine_cache: dict = {}  # asset_type → (engine, profile)
            def _get_entry_engine(asset_type: str):
                if asset_type not in _engine_cache:
                    # Strategy params override profile if provided
                    if strategy_params:
                        pr   = getattr(self.settings, "portfolio_rules", None)
                        eng  = EntryHealthEngine(
                            parameters=strategy_params,
                            buy_threshold=pr.entry_buy_threshold if pr else 75.0,
                            hard_gate_above_200dma=pr.hard_gate_above_200dma if pr else True,
                            hard_gate_no_strong_bear_macd=pr.hard_gate_no_strong_bear_macd if pr else True,
                            hard_gate_max_drawdown=pr.hard_gate_max_drawdown if pr else -15.0,
                        )
                        _engine_cache[asset_type] = (eng, None)
                    else:
                        eng, prof = load_profile_engine(asset_type, "entry", session)
                        _engine_cache[asset_type] = (eng, prof)
                return _engine_cache[asset_type][0]

            breadth_symbols = [w.symbol for w in watchlist]
            breadth_dfs = {sym: fetch_ohlcv(sym, period=self.settings.data.download_period) for sym in breadth_symbols[:20]}
            market_breadth = compute_market_breadth(breadth_symbols[:20], breadth_dfs)

            # Market Health Score — separate from stock scores
            mh_score, mh_deploy_pct, mh_deploy_label, mh_reasons, mh_components = \
                self._compute_market_health(market_breadth)

            results: List[ScanResult] = []
            scan_repo = ScanHistoryRepository(session)

            # Extract primitives from ORM objects before any inner DB ops
            # (avoids DetachedInstanceError when inner commits expire the session)
            watchlist_items = [
                {
                    "symbol": w.symbol,
                    "name": w.name or w.symbol,
                    "asset_type": w.asset_type,
                }
                for w in watchlist
            ]

            for item in watchlist_items:
                sym   = item["symbol"]
                name  = item["name"]
                atype = item["asset_type"]
                try:
                    df = fetch_ohlcv(sym, period=self.settings.data.download_period)
                    ind = compute_indicators(df, sym, self._benchmark_df, self._vix_df, drawdown_days=dd_days)
                    ind.breadth = market_breadth

                    health = _get_entry_engine(atype).compute(ind)

                    positions = pos_repo.get_by_symbol(sym, version_id=version_id)
                    chunks_held = len(positions)
                    has_position = chunks_held > 0
                    current_profit = 0.0
                    next_buy = None

                    if has_position:
                        avg_price = chunk_engine.compute_average_price(positions)
                        if avg_price > 0:
                            current_profit = (ind.price - avg_price) / avg_price * 100
                        next_buy = chunk_engine.get_next_buy_price(atype, avg_price, chunks_held)

                    try:
                        scan_repo.upsert(date.today(), sym, health.score, health.recommendation, version_id=version_id)
                    except Exception:
                        pass

                    results.append(ScanResult(
                        rank=0,
                        symbol=sym,
                        name=name,
                        asset_type=atype,
                        price=ind.price,
                        health_score=health.score,
                        max_score=health.max_score,
                        score_pct=health.score_pct,
                        recommendation=health.recommendation,
                        reasons=health.reasons,
                        component_scores=health.component_scores,
                        indicator=ind,
                        current_profit=current_profit,
                        has_position=has_position,
                        chunks_held=chunks_held,
                        next_buy_price=next_buy,
                        market_score=mh_score,
                        deploy_pct=mh_deploy_pct,
                        deploy_label=mh_deploy_label,
                        change_pct=ind.change_pct,
                        prev_close=ind.prev_close,
                    ))
                except Exception as e:
                    logger.error(f"Scan error for {sym}: {e}")
                    # Still fetch live price so CMP shows in the table
                    try:
                        from state_quant_engine.engine.indicators.data_fetcher import fetch_price_with_change
                        cmp, prev_close, change_pct = fetch_price_with_change(sym)
                    except Exception:
                        cmp, prev_close, change_pct = 0.0, 0.0, 0.0

                    err_msg = "Insufficient price history — need ≥30 days for indicators" \
                        if "Insufficient data" in str(e) or "30" in str(e) or len(str(e)) < 5 \
                        else str(e)

                    results.append(ScanResult(
                        rank=0, symbol=sym, name=name,
                        asset_type=atype, price=cmp, health_score=0.0,
                        max_score=100.0, score_pct=0.0, recommendation="WAIT",
                        reasons=[f"⚠ {err_msg}"], component_scores={}, error=err_msg,
                        change_pct=change_pct, prev_close=prev_close,
                    ))

            results.sort(key=lambda r: r.score_pct, reverse=True)
            for i, r in enumerate(results, 1):
                r.rank = i

            return results
        finally:
            session.close()
