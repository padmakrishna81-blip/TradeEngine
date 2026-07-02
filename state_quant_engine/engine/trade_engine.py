"""Entry, Hold, and Exit engines."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional
from state_quant_engine.engine.indicators.technical import IndicatorResult
from state_quant_engine.engine.health_score_engine import HealthScoreResult
from state_quant_engine.models.orm_models import Position


@dataclass
class TradeSignal:
    symbol: str
    action: str  # BUY / HOLD / WAIT / EXIT / NO_TRADE
    reason: str
    price: float
    chunk_no: int = 0
    quantity: float = 0.0


def _symbol_allocated_capital(symbol: str, asset_type: str, settings: Any) -> float:
    """
    Return the ₹ amount allocated to this specific symbol.

    Priority:
    1. symbol_allocations dict in settings (user-defined % of pool)
    2. Fall back: equal split of pool across watchlist symbols
    """
    allocs = getattr(settings, "symbol_allocations", {})
    total  = settings.etf_capital.total if asset_type == "ETF" else settings.stock_capital.total

    if symbol in allocs and allocs[symbol] > 0:
        return total * allocs[symbol] / 100

    # No explicit allocation — fall back to per-stock cap
    if asset_type == "STOCK":
        return min(
            total / (settings.stock_capital.num_stocks or 10),
            settings.stock_capital.max_per_stock or 100000,
        )
    # ETF fallback: equal split across 5 default ETFs
    return total / 5


class EntryEngine:
    """Decides whether to enter a position."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def evaluate(
        self,
        ind: IndicatorResult,
        health: HealthScoreResult,
        existing_chunks: int,
        available_capital: float,
        asset_type: str,
        deploy_pct: float = 100.0,
    ) -> TradeSignal:
        """Return a BUY, WAIT, or NO_TRADE signal.

        deploy_pct: market health deployment multiplier (0-100).
                    Reduces chunk size proportionally when market is weak.
        """
        hs = self.settings.health_scores

        if not ind.is_valid:
            return TradeSignal(ind.symbol, "NO_TRADE", "Invalid data", ind.price)

        if ind.vix > self.settings.exit_strategies.get("risk", {}).get("vix_threshold", 25):
            return TradeSignal(ind.symbol, "NO_TRADE", f"VIX too high ({ind.vix:.1f})", ind.price)

        if health.score_pct < hs.buy_threshold:
            return TradeSignal(
                ind.symbol, "WAIT",
                f"Health {health.score_pct:.1f}% below BUY threshold {hs.buy_threshold}%",
                ind.price,
            )

        cap_cfg = self.settings.etf_capital if asset_type == "ETF" else self.settings.stock_capital

        if existing_chunks >= cap_cfg.num_chunks:
            return TradeSignal(ind.symbol, "HOLD", "All chunks deployed", ind.price)

        next_chunk = existing_chunks + 1
        chunk_idx  = existing_chunks  # 0-based index into chunk_percentages

        # Symbol-specific allocated capital
        symbol_capital = _symbol_allocated_capital(ind.symbol, asset_type, self.settings)

        # Chunk percentage from config (user-defined per chunk)
        chunk_pcts = cap_cfg.chunk_percentages
        chunk_pct  = (chunk_pcts[chunk_idx] if chunk_idx < len(chunk_pcts)
                      else chunk_pcts[-1]) / 100

        # Apply market health deployment multiplier
        deploy_mult = max(0.0, min(1.0, deploy_pct / 100))
        alloc = symbol_capital * chunk_pct * deploy_mult

        if available_capital < alloc:
            return TradeSignal(ind.symbol, "WAIT",
                               f"Insufficient capital for chunk {next_chunk} "
                               f"(need ₹{alloc:,.0f}, available ₹{available_capital:,.0f})",
                               ind.price)

        qty = alloc / ind.price if ind.price > 0 else 0
        market_note = f" [Market deploy {deploy_pct:.0f}%]" if deploy_pct < 100 else ""
        return TradeSignal(
            ind.symbol, "BUY",
            f"Health {health.score_pct:.1f}% ≥ {hs.buy_threshold}% — "
            f"Chunk {next_chunk}: ₹{alloc:,.0f} ({chunk_pct*100:.0f}% of ₹{symbol_capital:,.0f} allocated){market_note}",
            ind.price, chunk_no=next_chunk, quantity=qty,
        )


class HoldEngine:
    """Decides whether to continue holding a position."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def evaluate(
        self,
        ind: IndicatorResult,
        health: HealthScoreResult,
        position: Position,
    ) -> TradeSignal:
        """Return HOLD or EXIT signal for an open position."""
        hs = self.settings.health_scores

        if health.score_pct >= hs.hold_threshold and ind.macd_line >= ind.macd_signal:
            return TradeSignal(
                ind.symbol, "HOLD",
                f"Health {health.score_pct:.1f}% >= {hs.hold_threshold}% and MACD bullish",
                ind.price,
            )

        if health.score_pct < hs.exit_threshold:
            return TradeSignal(
                ind.symbol, "EXIT",
                f"Health {health.score_pct:.1f}% below exit threshold {hs.exit_threshold}%",
                ind.price,
            )

        return TradeSignal(ind.symbol, "WATCH", f"Health {health.score_pct:.1f}% - monitoring", ind.price)


class ExitEngine:
    """Multi-strategy dynamic exit engine."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self.exit_cfg = settings.exit_strategies

    def evaluate(
        self,
        ind: IndicatorResult,
        health: HealthScoreResult,
        position: Position,
        holding_days: int,
    ) -> TradeSignal:
        """Check all exit strategies and return EXIT or HOLD signal."""
        current_profit_pct = position.current_profit

        # A: Trailing profit exit
        trailing_cfg = self.exit_cfg.get("trailing", {})
        if trailing_cfg.get("enabled", True):
            profit_threshold = float(trailing_cfg.get("profit_threshold", 5.0))
            trail_pct = float(trailing_cfg.get("trail_percent", 2.0))
            if position.highest_profit >= profit_threshold:
                trail_from_high = position.highest_profit - current_profit_pct
                if trail_from_high >= trail_pct:
                    return TradeSignal(
                        ind.symbol, "EXIT",
                        f"Trailing exit: profit dropped {trail_from_high:.1f}% from high {position.highest_profit:.1f}%",
                        ind.price,
                    )

        # B: Momentum exit
        momentum_cfg = self.exit_cfg.get("momentum", {})
        if momentum_cfg.get("enabled", True):
            if ind.macd_line < ind.macd_signal and ind.price < ind.ema20:
                return TradeSignal(
                    ind.symbol, "EXIT",
                    "Momentum exit: MACD bearish and price below EMA20",
                    ind.price,
                )

        # C: Health exit
        health_cfg = self.exit_cfg.get("health", {})
        if health_cfg.get("enabled", True):
            min_score = float(health_cfg.get("min_score", 35))
            if health.score_pct < min_score:
                return TradeSignal(
                    ind.symbol, "EXIT",
                    f"Health exit: score {health.score_pct:.1f}% below minimum {min_score}%",
                    ind.price,
                )

        # D: Time exit
        time_cfg = self.exit_cfg.get("time", {})
        if time_cfg.get("enabled", True):
            max_days = int(time_cfg.get("max_days", 90))
            min_profit = float(time_cfg.get("min_profit", 0))
            if holding_days >= max_days and current_profit_pct < min_profit:
                return TradeSignal(
                    ind.symbol, "EXIT",
                    f"Time exit: {holding_days} days held, profit {current_profit_pct:.1f}% below minimum",
                    ind.price,
                )

        # E: Risk exit
        risk_cfg = self.exit_cfg.get("risk", {})
        if risk_cfg.get("enabled", True):
            vix_threshold = float(risk_cfg.get("vix_threshold", 25))
            atr_mult = float(risk_cfg.get("atr_multiplier", 2.5))
            atr_pct = (ind.atr14 / ind.price * 100) if ind.price > 0 else 0
            if ind.vix > vix_threshold and atr_pct > atr_mult:
                return TradeSignal(
                    ind.symbol, "EXIT",
                    f"Risk exit: VIX={ind.vix:.1f} and ATR={atr_pct:.1f}%",
                    ind.price,
                )

        return TradeSignal(ind.symbol, "HOLD", "No exit conditions triggered", ind.price)


class ChunkEngine:
    """Manages multi-chunk entry strategy and next buy triggers."""

    def __init__(self, settings: Any) -> None:
        self.settings = settings

    def get_next_buy_price(self, asset_type: str, current_avg: float, chunks_bought: int) -> Optional[float]:
        """Calculate the next chunk buy trigger price."""
        if asset_type == "ETF":
            cfg = self.settings.etf_capital
        else:
            cfg = self.settings.stock_capital

        if chunks_bought >= cfg.num_chunks:
            return None

        triggers = cfg.next_buy_triggers
        if chunks_bought < len(triggers):
            drop_pct = triggers[chunks_bought] / 100
        else:
            drop_pct = triggers[-1] / 100

        return current_avg * (1 - drop_pct)

    def compute_average_price(self, positions: list) -> float:
        """Compute weighted average price across all open chunks."""
        total_cost = sum(p.buy_price * p.quantity for p in positions)
        total_qty = sum(p.quantity for p in positions)
        return total_cost / total_qty if total_qty > 0 else 0.0
