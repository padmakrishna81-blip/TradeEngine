"""Portfolio service - aggregates position data and P&L."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import date, datetime
from loguru import logger
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.position_repository import PositionRepository
from state_quant_engine.repositories.trade_log_repository import TradeLogRepository
from state_quant_engine.engine.indicators.data_fetcher import fetch_current_price, fetch_price_with_change


# ---------------------------------------------------------------------------
# Smart exit signal constants
# ---------------------------------------------------------------------------
_SIG_STRONG_HOLD   = "STRONG HOLD"
_SIG_HOLD          = "HOLD"
_SIG_PARTIAL_EXIT  = "PARTIAL EXIT"
_SIG_FULL_EXIT     = "FULL EXIT"
_SIG_WATCH         = "WATCH"

_SIG_COLORS = {
    _SIG_STRONG_HOLD:  {"bg": "#00C853", "fg": "#000"},
    _SIG_HOLD:         {"bg": "#2979FF", "fg": "#fff"},
    _SIG_WATCH:        {"bg": "#FF6D00", "fg": "#fff"},
    _SIG_PARTIAL_EXIT: {"bg": "#E65100", "fg": "#fff"},
    _SIG_FULL_EXIT:    {"bg": "#D50000", "fg": "#fff"},
}


def compute_exit_signal(
    profit_pct: float,
    highest_profit: float,
    health_pct: float,
    trend: str,
    risk: str,
    settings: Any,
) -> tuple[str, str]:
    """
    Determine the smart exit signal for an open position.

    Decision tree:
    1. STRONG HOLD  — profit_threshold hit BUT health >= strong_hold_min AND trend == Bullish
    2. PARTIAL EXIT — profit_threshold hit, health is OK (hold_threshold..strong_hold_min)
    3. FULL EXIT    — profit_threshold hit AND health < hold_threshold  OR  health < exit_threshold
    4. HOLD         — no threshold hit, health >= hold_threshold
    5. WATCH        — below hold_threshold, above exit_threshold
    """
    pm  = settings.profit_management
    hs  = settings.health_scores
    pt  = pm.profit_threshold

    reasons = []

    profit_triggered = profit_pct >= pt or highest_profit >= pt

    if profit_triggered:
        reasons.append(f"profit {profit_pct:.1f}% ≥ threshold {pt:.0f}%")

        # Condition 1 — super positive: strong health + bullish trend
        if health_pct >= pm.strong_hold_health_min and trend == pm.strong_hold_trend:
            return _SIG_STRONG_HOLD, (
                f"Profit threshold hit but health {health_pct:.0f}% is strong "
                f"and trend is {trend} — hold for more gains"
            )

        # Condition 3 — health poor → full exit
        if health_pct < hs.hold_threshold:
            reasons.append(f"health {health_pct:.0f}% < {hs.hold_threshold:.0f}%")
            if risk == "RISKY":
                reasons.append("risk rated RISKY")
            return _SIG_FULL_EXIT, "; ".join(reasons)

        # Condition 2 — health ok → partial exit
        reasons.append(f"health {health_pct:.0f}% is moderate")
        return _SIG_PARTIAL_EXIT, "; ".join(reasons)

    # No profit threshold — evaluate health
    if health_pct < hs.exit_threshold:
        return _SIG_FULL_EXIT, f"Health {health_pct:.0f}% below exit threshold {hs.exit_threshold:.0f}%"

    if health_pct < hs.hold_threshold:
        return _SIG_WATCH, f"Health {health_pct:.0f}% between watch and hold thresholds"

    return _SIG_HOLD, f"Health {health_pct:.0f}% ≥ hold threshold; no exit trigger"


@dataclass
class PortfolioSummary:
    total_capital: float = 0.0
    allocated: float = 0.0
    available: float = 0.0
    current_value: float = 0.0
    mtm: float = 0.0
    mtm_pct: float = 0.0
    open_positions: int = 0
    buy_signals: int = 0
    hold_signals: int = 0
    exit_signals: int = 0
    positions: List[Dict] = field(default_factory=list)
    version_id: int = 1


class PortfolioService:
    """Computes portfolio metrics from open positions."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def get_summary(self, scan_results: Optional[List] = None, version_id: int = 1) -> PortfolioSummary:
        """Build portfolio summary from DB positions and scan results."""
        summary = PortfolioSummary(version_id=version_id)
        summary.total_capital = (
            self.settings.etf_capital.total + self.settings.stock_capital.total
        )

        session = get_session()
        try:
            repo = PositionRepository(session)
            positions = repo.get_open_positions(version_id=version_id)

            total_cost = 0.0
            total_value = 0.0
            pos_details = []

            for pos in positions:
                current_price, prev_close, day_chg = fetch_price_with_change(pos.symbol)
                if current_price == 0.0:
                    current_price = fetch_current_price(pos.symbol)
                if current_price > 0:
                    pos.current_price = current_price
                    cost = pos.buy_price * pos.quantity
                    value = current_price * pos.quantity
                    profit_pct = (current_price - pos.buy_price) / pos.buy_price * 100 if pos.buy_price > 0 else 0

                    if profit_pct > pos.highest_profit:
                        pos.highest_profit = profit_pct
                    pos.current_profit = profit_pct
                    session.commit()

                    total_cost += cost
                    total_value += value
                    pos_details.append({
                        "symbol": pos.symbol,
                        "cycle": pos.cycle,
                        "chunk": pos.chunk_no,
                        "qty": pos.quantity,
                        "buy_price": pos.buy_price,
                        "current_price": current_price,
                        "prev_close": prev_close,
                        "day_chg": day_chg,
                        "cost": cost,
                        "value": value,
                        "profit_pct": profit_pct,
                        "highest_profit": pos.highest_profit,
                        "buy_date": pos.buy_date,
                        # placeholders — enriched below after loop
                        "health_pct": 0.0,
                        "trend": "",
                        "risk": "",
                        "trend_reason": "",
                        "risk_reason": "",
                        "exit_signal": "",
                        "exit_reason": "",
                    })

            summary.allocated = total_cost
            summary.available = summary.total_capital - total_cost
            summary.current_value = total_value
            summary.mtm = total_value - total_cost
            summary.mtm_pct = (summary.mtm / total_cost * 100) if total_cost > 0 else 0.0
            summary.open_positions = len(positions)
            summary.positions = pos_details

            # Enrich positions with scan result data (health, trend, risk, exit signal)
            if scan_results:
                scan_map = {r.symbol: r for r in scan_results}
                for pos in pos_details:
                    sr = scan_map.get(pos["symbol"])
                    if sr:
                        pos["health_pct"]   = sr.score_pct
                        pos["trend"]        = sr.trend
                        pos["risk"]         = sr.risk
                        pos["trend_reason"] = sr.trend_reason
                        pos["risk_reason"]  = sr.risk_reason
                        sig, reason = compute_exit_signal(
                            profit_pct=pos["profit_pct"],
                            highest_profit=pos["highest_profit"],
                            health_pct=sr.score_pct,
                            trend=sr.trend,
                            risk=sr.risk,
                            settings=self.settings,
                        )
                        pos["exit_signal"] = sig
                        pos["exit_reason"] = reason

                for r in scan_results:
                    if r.recommendation == "BUY":
                        summary.buy_signals += 1
                    elif r.recommendation == "HOLD":
                        summary.hold_signals += 1
                    elif r.recommendation == "EXIT":
                        summary.exit_signals += 1

            return summary
        finally:
            session.close()

    def analyse_positions(self, version_id: int = 1) -> list:
        """
        Run indicators + health score + exit signals for all currently held symbols.
        Returns an enriched positions list (same dict shape as get_summary().positions).
        Independent of the Scanner — works any time, no prior scan needed.
        """
        from state_quant_engine.engine.indicators.data_fetcher import fetch_ohlcv
        from state_quant_engine.engine.indicators.technical import compute_indicators
        from state_quant_engine.engine.health_score_engine import HealthScoreEngine
        from state_quant_engine.services.assessment_service import assess_trend_and_risk
        from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository
        from state_quant_engine.services.scanner_service import ScanResult

        session = get_session()
        try:
            hp_repo = HealthParameterRepository(session)
            params  = hp_repo.get_enabled()
            param_list = [
                {"parameter_name": p.parameter_name, "weight": p.weight,
                 "enabled": p.enabled, "threshold": p.threshold}
                for p in params
            ]
            hs = self.settings.health_scores
            health_engine = HealthScoreEngine(
                param_list, hs.buy_threshold, hs.hold_threshold,
                hs.watch_threshold, hs.exit_threshold,
            )

            summary = self.get_summary(version_id=version_id)
            if not summary.positions:
                return []

            # Group positions by symbol
            symbol_set = list({p["symbol"] for p in summary.positions})

            # Build lightweight ScanResult-like objects for assessment
            scan_results = []
            for sym in symbol_set:
                try:
                    df = fetch_ohlcv(sym, period=self.settings.data.download_period)
                    ind = compute_indicators(df, sym)
                    health = health_engine.compute(ind)
                    sr = ScanResult(
                        rank=0, symbol=sym, name=sym, asset_type="STOCK",
                        price=ind.price, health_score=health.score,
                        max_score=health.max_score, score_pct=health.score_pct,
                        recommendation=health.recommendation,
                        reasons=health.reasons, component_scores=health.component_scores,
                        indicator=ind,
                    )
                    scan_results.append(sr)
                except Exception as e:
                    logger.warning(f"analyse_positions: failed for {sym}: {e}")

            # Web-based trend/risk assessment (no API key needed)
            if scan_results:
                assess_trend_and_risk(scan_results)

            # Enrich positions
            scan_map = {r.symbol: r for r in scan_results}
            for pos in summary.positions:
                sr = scan_map.get(pos["symbol"])
                if sr:
                    pos["health_pct"]   = sr.score_pct
                    pos["trend"]        = sr.trend
                    pos["risk"]         = sr.risk
                    pos["trend_reason"] = sr.trend_reason
                    pos["risk_reason"]  = sr.risk_reason
                    sig, reason = compute_exit_signal(
                        profit_pct=pos["profit_pct"],
                        highest_profit=pos["highest_profit"],
                        health_pct=sr.score_pct,
                        trend=sr.trend,
                        risk=sr.risk,
                        settings=self.settings,
                    )
                    pos["exit_signal"] = sig
                    pos["exit_reason"] = reason

            return summary.positions
        finally:
            session.close()

    def execute_trade(
        self, symbol: str, action: str, price: float, quantity: float,
        remarks: str = "", version_id: int = 1,
    ) -> None:
        """Record a trade and update position state."""
        session = get_session()
        try:
            trade_repo = TradeLogRepository(session)
            pos_repo = PositionRepository(session)

            trade_repo.log_trade(symbol, action, price, quantity, remarks, version_id=version_id)

            if action == "BUY":
                cycle = pos_repo.get_max_cycle(symbol, version_id=version_id)
                open_chunks = pos_repo.get_by_symbol(symbol, version_id=version_id)
                chunk_no = len(open_chunks) + 1

                if not open_chunks:
                    cycle = cycle + 1

                pos = pos_repo.get_by_symbol_cycle_chunk(symbol, cycle or 1, chunk_no, version_id=version_id)
                if not pos:
                    from state_quant_engine.models.orm_models import Position
                    pos = Position(
                        symbol=symbol,
                        cycle=cycle or 1,
                        chunk_no=chunk_no,
                        quantity=quantity,
                        buy_price=price,
                        buy_date=date.today(),
                        current_price=price,
                        highest_price=price,
                        status="OPEN",
                        version_id=version_id,
                    )
                    session.add(pos)
                    session.commit()

            elif action in ("EXIT", "PARTIAL_EXIT"):
                open_positions = pos_repo.get_by_symbol(symbol, version_id=version_id)
                for pos in open_positions:
                    pos.status = "CLOSED"
                    pos.current_price = price
                session.commit()

        finally:
            session.close()
