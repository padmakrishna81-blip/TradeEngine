"""Backtesting engine."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import date
import numpy as np
import pandas as pd
from loguru import logger
from state_quant_engine.engine.indicators.data_fetcher import fetch_ohlcv
from state_quant_engine.engine.indicators.technical import compute_indicators, _ema, _rsi, _macd, _adx, _atr
from state_quant_engine.engine.health_score_engine import HealthScoreEngine


@dataclass
class BacktestResult:
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    win_rate: float = 0.0
    cagr: float = 0.0
    max_drawdown: float = 0.0
    sharpe: float = 0.0
    profit_factor: float = 0.0
    final_equity: float = 0.0
    trades: List[Dict] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)
    profit_curve: List[Dict] = field(default_factory=list)
    error: Optional[str] = None


def run_backtest(
    symbol: str,
    asset_type: str,
    capital: float,
    start_date: date,
    end_date: date,
    chunk_strategy: str,
    settings: Any,
) -> BacktestResult:
    """Run a vectorized backtest for a single symbol."""
    result = BacktestResult()
    try:
        df = fetch_ohlcv(symbol, period="5y")
        if df.empty:
            result.error = f"No data for {symbol}"
            return result

        mask = (df.index.date >= start_date) & (df.index.date <= end_date)
        df = df[mask].copy()
        if len(df) < 50:
            result.error = "Insufficient historical data for selected date range"
            return result

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        ema20 = _ema(close, 20)
        ema50 = _ema(close, 50)
        ema200_len = min(200, len(close) - 1)
        ema200 = _ema(close, ema200_len)
        rsi = _rsi(close)
        macd_line, macd_signal, _ = _macd(close)
        adx = _adx(high, low, close)

        equity = capital
        position = 0.0
        avg_cost = 0.0
        chunks = 0
        highest_equity = equity
        max_dd = 0.0
        equity_curve = []
        trades_log = []
        profits = []

        if chunk_strategy == "Aggressive":
            chunk_pcts = [0.4, 0.3, 0.3]
        elif chunk_strategy == "Conservative":
            chunk_pcts = [0.2, 0.2, 0.2, 0.2, 0.2]
        else:
            chunk_pcts = [0.33, 0.33, 0.34]

        max_chunks = len(chunk_pcts)
        buy_threshold = settings.health_scores.buy_threshold
        exit_threshold = settings.health_scores.exit_threshold

        health_params = settings.health_parameters
        he = HealthScoreEngine(health_params, buy_threshold=buy_threshold, exit_threshold=exit_threshold,
                                hold_threshold=settings.health_scores.hold_threshold,
                                watch_threshold=settings.health_scores.watch_threshold)

        for i in range(50, len(df)):
            current_price = float(close.iloc[i])
            current_date = df.index[i].date()
            slice_df = df.iloc[:i+1].copy()

            from state_quant_engine.engine.indicators.technical import IndicatorResult
            ind = IndicatorResult(symbol=symbol)
            ind.price = current_price
            ind.ema20 = float(ema20.iloc[i])
            ind.ema50 = float(ema50.iloc[i])
            ind.ema200 = float(ema200.iloc[i])
            ind.rsi14 = float(rsi.iloc[i]) if not pd.isna(rsi.iloc[i]) else 50.0
            ind.macd_line = float(macd_line.iloc[i])
            ind.macd_signal = float(macd_signal.iloc[i])
            ind.adx14 = float(adx.iloc[i]) if not pd.isna(adx.iloc[i]) else 0.0
            ind.volume_ratio = 1.0
            ind.relative_strength = 1.0
            ind.vix = 15.0
            ind.breadth = 0.6
            ind.drawdown_pct = 0.0

            health = he.compute(ind)
            score_pct = health.score_pct

            current_value = equity + position * current_price
            if current_value > highest_equity:
                highest_equity = current_value
            dd = (highest_equity - current_value) / highest_equity * 100 if highest_equity > 0 else 0
            if dd > max_dd:
                max_dd = dd

            equity_curve.append({
                "date": current_date,
                "equity": current_value,
                "benchmark": capital * (current_price / float(close.iloc[50])),
            })

            if score_pct >= buy_threshold and chunks < max_chunks:
                alloc = equity * chunk_pcts[chunks]
                if alloc > 0 and equity >= alloc:
                    qty = alloc / current_price
                    total_cost = avg_cost * position + alloc
                    position += qty
                    equity -= alloc
                    avg_cost = total_cost / position if position > 0 else current_price
                    chunks += 1
                    trades_log.append({
                        "date": current_date, "action": f"BUY C{chunks}",
                        "price": current_price, "qty": round(qty, 4),
                        "equity": round(equity + position * current_price, 2),
                    })

            elif position > 0 and score_pct < exit_threshold:
                profit_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
                proceeds = position * current_price
                equity += proceeds
                profits.append(profit_pct)
                trades_log.append({
                    "date": current_date, "action": "EXIT",
                    "price": current_price, "qty": round(position, 4),
                    "profit_pct": round(profit_pct, 2),
                    "equity": round(equity, 2),
                })
                position = 0.0
                avg_cost = 0.0
                chunks = 0

        if position > 0:
            final_price = float(close.iloc[-1])
            profit_pct = (final_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
            equity += position * final_price
            profits.append(profit_pct)

        result.final_equity = equity
        days = (end_date - start_date).days
        years = days / 365.25
        if years > 0:
            result.cagr = ((equity / capital) ** (1 / years) - 1) * 100

        result.max_drawdown = max_dd
        result.total_trades = len([t for t in trades_log if t["action"] == "EXIT"])
        result.win_trades = sum(1 for p in profits if p > 0)
        result.loss_trades = sum(1 for p in profits if p <= 0)
        result.win_rate = (result.win_trades / result.total_trades * 100) if result.total_trades > 0 else 0

        wins = [p for p in profits if p > 0]
        losses = [abs(p) for p in profits if p < 0]
        result.profit_factor = sum(wins) / sum(losses) if losses else float("inf")

        if equity_curve:
            eq_vals = [e["equity"] for e in equity_curve]
            eq_series = pd.Series(eq_vals)
            daily_returns = eq_series.pct_change().dropna()
            if daily_returns.std() > 0:
                result.sharpe = (daily_returns.mean() / daily_returns.std()) * (252 ** 0.5)

        result.trades = trades_log
        result.equity_curve = equity_curve
        result.profit_curve = [{"trade": i+1, "profit_pct": p} for i, p in enumerate(profits)]

    except Exception as e:
        logger.error(f"Backtest error: {e}")
        result.error = str(e)

    return result
