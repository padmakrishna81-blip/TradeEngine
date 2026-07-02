"""Portfolio service - aggregates position data and P&L + Hold Health scoring."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime
from loguru import logger
from state_quant_engine.database.connection import get_session
from state_quant_engine.repositories.position_repository import PositionRepository
from state_quant_engine.repositories.trade_log_repository import TradeLogRepository
from state_quant_engine.engine.indicators.data_fetcher import fetch_current_price, fetch_price_with_change


# ---------------------------------------------------------------------------
# Portfolio action constants  (HOLD / AVG / EXIT only — spec §10)
# ---------------------------------------------------------------------------

_ACT_HOLD = "HOLD"
_ACT_AVG  = "AVG"
_ACT_EXIT = "EXIT"

_SIG_COLORS = {
    "HOLD":         {"bg": "#2979FF", "fg": "#fff"},
    "AVG":          {"bg": "#00C853", "fg": "#000"},
    "EXIT":         {"bg": "#D50000", "fg": "#fff"},
    # legacy labels kept for backward-compat display
    "STRONG HOLD":  {"bg": "#00C853", "fg": "#000"},
    "PARTIAL EXIT": {"bg": "#E65100", "fg": "#fff"},
    "FULL EXIT":    {"bg": "#D50000", "fg": "#fff"},
    "WATCH":        {"bg": "#FF6D00", "fg": "#fff"},
}

# Old aliases still used in some UI pages
_SIG_STRONG_HOLD  = "HOLD"
_SIG_HOLD         = "HOLD"
_SIG_WATCH        = "WATCH"
_SIG_PARTIAL_EXIT = "EXIT"
_SIG_FULL_EXIT    = "EXIT"


def _trailing_buffer(hold_health: float, rules: Any) -> float:
    """Return the dynamic trailing buffer % based on hold health and config."""
    buffers = getattr(rules, "trailing_buffers", [])
    for tier in sorted(buffers, key=lambda t: t["min_health"], reverse=True):
        if hold_health >= tier["min_health"]:
            return float(tier["buffer"])
    return 0.75   # fallback


def compute_portfolio_action(
    profit_pct: float,
    highest_profit: float,
    hold_health_pct: float,
    asset_type: str,
    current_chunk: int,
    max_chunks: int,
    avg_price: float,
    current_price: float,
    next_trigger_pct: float,
    settings: Any,
) -> tuple[str, str]:
    """
    Three-layer decision:  EXIT first → AVG second → HOLD

    Profit % is factored into the effective exit score:
      effective_exit_score = hold_health_pct × (1 - profit_weight/100)
                           + profit_contribution × (profit_weight/100)
    where profit_contribution = min(profit_pct / profit_exit_threshold, 1.0) × 100
    When profit exceeds profit_exit_threshold the score gets boosted toward exit.
    """
    rules      = getattr(settings, "portfolio_rules", None)
    exit_thr   = getattr(rules, "hold_health_exit_threshold", 45) if rules else 45
    avg_min    = getattr(rules, "avg_health_min", 60) if rules else 60
    hard_stock = getattr(rules, "hard_stop_stock", -8.0) if rules else -8.0
    hard_etf   = getattr(rules, "hard_stop_etf", -6.0) if rules else -6.0
    hard_stop  = hard_etf if asset_type == "ETF" else hard_stock
    p_exit_thr = getattr(rules, "profit_exit_threshold", 10.0) if rules else 10.0
    p_weight   = getattr(rules, "profit_exit_weight", 20.0) if rules else 20.0  # 0-100

    # ── Profit contribution to effective health score ─────────────────────
    # If profit >= threshold, profit_contribution = 100 (healthy to exit).
    # Blended score keeps the position feeling healthy longer when profitable.
    if p_weight > 0 and p_exit_thr > 0:
        profit_contrib = min(max(profit_pct / p_exit_thr, 0.0), 1.0) * 100
        effective_health = (hold_health_pct * (1 - p_weight / 100)
                            + profit_contrib * (p_weight / 100))
    else:
        effective_health = hold_health_pct

    profit_note = ""
    if profit_pct >= p_exit_thr:
        profit_note = f" (profit {profit_pct:.1f}% ≥ {p_exit_thr:.0f}% threshold)"

    # ── STEP 1: EXIT checks ───────────────────────────────────────────────
    # E1 — Effective health breakdown (includes profit contribution)
    if effective_health < exit_thr:
        return _ACT_EXIT, (
            f"Effective health {effective_health:.0f}% < {exit_thr:.0f}% exit threshold"
            + profit_note
        )

    # E3 — Hard stop-loss
    if profit_pct <= hard_stop:
        return _ACT_EXIT, f"Hard stop-loss hit: {profit_pct:.1f}% ≤ {hard_stop:.1f}%"

    # E2 — Trailing profit stop
    if highest_profit > 0:
        buf = _trailing_buffer(effective_health, rules)
        trail_exit_level = highest_profit - buf
        if profit_pct <= trail_exit_level:
            return _ACT_EXIT, (
                f"Trailing stop: peak {highest_profit:.1f}% − buffer {buf:.1f}% = "
                f"{trail_exit_level:.1f}%, current {profit_pct:.1f}%"
                + profit_note
            )

    # ── STEP 2: AVG check ─────────────────────────────────────────────────
    if (hold_health_pct >= avg_min
            and current_chunk < max_chunks
            and avg_price > 0):
        price_drop_pct = (current_price - avg_price) / avg_price * 100
        if price_drop_pct <= next_trigger_pct:
            return _ACT_AVG, (
                f"Health {hold_health_pct:.0f}% ≥ {avg_min:.0f}%, "
                f"price dropped {price_drop_pct:.1f}% (trigger {next_trigger_pct:.1f}%), "
                f"chunk {current_chunk}/{max_chunks}"
            )

    # ── STEP 3: HOLD ──────────────────────────────────────────────────────
    return _ACT_HOLD, (
        f"Health {hold_health_pct:.0f}% — hold position"
        + (f"; profit {profit_pct:.1f}% (target {p_exit_thr:.0f}%)" if profit_pct > 0 else "")
    )


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

            # ── Compute Hold Health per symbol and derive HOLD/AVG/EXIT action ──
            # Build indicator + hold health per unique symbol
            try:
                from state_quant_engine.engine.indicators.data_fetcher import fetch_ohlcv
                from state_quant_engine.engine.indicators.technical import compute_indicators
                from state_quant_engine.engine.health_score_engine import HoldHealthEngine
                from state_quant_engine.repositories.health_parameter_repository import HealthParameterRepository

                hp_session = get_session()
                try:
                    from state_quant_engine.repositories.health_parameter_repository import SCOPE_HOLD
                    hp_repo = HealthParameterRepository(hp_session)
                    params  = hp_repo.get_enabled_for_hold()
                    param_list = [
                        {"parameter_name": p.parameter_name, "weight": p.weight,
                         "enabled": p.enabled, "threshold": p.threshold}
                        for p in params
                    ]
                finally:
                    hp_session.close()

                hold_engine = HoldHealthEngine(parameters=param_list)
                cap_cfg_etf = self.settings.etf_capital
                cap_cfg_stk = self.settings.stock_capital

                for pos in pos_details:
                    sym = pos["symbol"]
                    try:
                        df  = fetch_ohlcv(sym, period=self.settings.data.download_period)
                        ind = compute_indicators(df, sym,
                                                 drawdown_days=self.settings.data.drawdown_days)
                        hold_result = hold_engine.compute(ind, profit_pct=pos["profit_pct"])
                        hold_pct    = hold_result.score_pct

                        # Determine max chunks and next trigger for this symbol
                        asset_type = pos.get("asset_type", "STOCK")
                        cap_cfg    = cap_cfg_etf if asset_type == "ETF" else cap_cfg_stk
                        max_chunks = cap_cfg.num_chunks

                        # Count open chunks for this symbol
                        all_chunks = [p for p in pos_details if p["symbol"] == sym]
                        current_chunk = len(all_chunks)

                        triggers = cap_cfg.next_buy_triggers
                        next_trig = -(triggers[current_chunk] if current_chunk < len(triggers)
                                      else triggers[-1])

                        action, reason = compute_portfolio_action(
                            profit_pct=pos["profit_pct"],
                            highest_profit=pos["highest_profit"],
                            hold_health_pct=hold_pct,
                            asset_type=asset_type,
                            current_chunk=current_chunk,
                            max_chunks=max_chunks,
                            avg_price=pos["buy_price"],
                            current_price=pos["current_price"],
                            next_trigger_pct=next_trig,
                            settings=self.settings,
                        )
                        pos["hold_health_pct"]      = hold_pct
                        pos["health_pct"]           = hold_pct
                        pos["hold_component_scores"] = hold_result.component_scores
                        pos["hold_reasons"]         = hold_result.reasons
                        pos["exit_signal"]          = action
                        pos["exit_reason"]          = reason
                    except Exception as e:
                        logger.warning(f"Hold health failed for {sym}: {e}")

            except Exception as e:
                logger.warning(f"Hold health batch failed: {e}")

            # Merge trend/risk from scan results if available (from last run)
            if scan_results:
                scan_map = {r.symbol: r for r in scan_results}
                for pos in pos_details:
                    sr = scan_map.get(pos["symbol"])
                    if sr:
                        pos["trend"]        = sr.trend
                        pos["risk"]         = sr.risk
                        pos["trend_reason"] = sr.trend_reason
                        pos["risk_reason"]  = sr.risk_reason

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
