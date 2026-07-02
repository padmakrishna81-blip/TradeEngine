"""Technical indicator calculations."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class IndicatorResult:
    """Container for all computed indicator values."""
    symbol: str
    price: float = 0.0
    ema20: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    rsi14: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    adx14: float = 0.0
    atr14: float = 0.0
    volume: float = 0.0
    volume_avg20: float = 0.0
    volume_ratio: float = 1.0
    drawdown_pct: float = 0.0
    swing_high: float = 0.0
    drawdown_days: int = 60          # spec requires 60-day high for drawdown
    prev_close: float = 0.0
    change_pct: float = 0.0
    relative_strength: float = 1.0
    rs_diff_20: float = 0.0          # stock 20-day return minus Nifty 20-day return (%)
    macd_hist_slope: float = 0.0     # slope of last 3 histogram bars (+ve = rising)
    vix: float = 15.0
    breadth: float = 0.5
    pct_from_200dma: float = 0.0     # ((close - dma200) / dma200) * 100
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.price > 0


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    # When avg_loss is 0 (no down moves), RSI = 100
    rsi = avg_gain.copy()
    zero_loss = avg_loss == 0
    nonzero_loss = ~zero_loss
    rs = avg_gain[nonzero_loss] / avg_loss[nonzero_loss]
    rsi[nonzero_loss] = 100 - (100 / (1 + rs))
    rsi[zero_loss] = 100.0
    return rsi


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = _ema(close, fast)
    slow_ema = _ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_di = 100 * pd.Series(plus_dm, index=close.index).ewm(span=period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=close.index).ewm(span=period, adjust=False).mean() / atr

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_indicators(df: pd.DataFrame, symbol: str, benchmark_df: Optional[pd.DataFrame] = None,
                        vix_df: Optional[pd.DataFrame] = None, drawdown_days: int = 52) -> IndicatorResult:
    """Compute all technical indicators from OHLCV DataFrame."""
    result = IndicatorResult(symbol=symbol)

    if df.empty or len(df) < 30:
        result.error = f"Insufficient data for {symbol} (rows={len(df)})"
        return result

    try:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        result.price = float(close.iloc[-1])

        # Previous close and day change — use fast_info for accuracy
        try:
            from state_quant_engine.engine.indicators.data_fetcher import fetch_price_with_change
            cmp, prev_close, change_pct = fetch_price_with_change(symbol)
            if cmp > 0:
                result.price = cmp         # override with live price
            result.prev_close  = prev_close
            result.change_pct  = change_pct
        except Exception:
            # Fallback: use last two OHLCV rows
            if len(close) >= 2:
                result.prev_close = float(close.iloc[-2])
                result.change_pct = ((result.price - result.prev_close)
                                     / result.prev_close * 100
                                     if result.prev_close > 0 else 0.0)

        result.ema20 = float(_ema(close, 20).iloc[-1])
        result.ema50 = float(_ema(close, 50).iloc[-1])
        result.ema200 = float(_ema(close, 200).iloc[-1]) if len(close) >= 200 else float(_ema(close, len(close)).iloc[-1])

        rsi_series = _rsi(close, 14)
        result.rsi14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

        macd_line, macd_signal, macd_hist = _macd(close)
        result.macd_line = float(macd_line.iloc[-1])
        result.macd_signal = float(macd_signal.iloc[-1])
        result.macd_histogram = float(macd_hist.iloc[-1])

        adx = _adx(high, low, close, 14)
        result.adx14 = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0

        atr = _atr(high, low, close, 14)
        result.atr14 = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0

        result.volume = float(volume.iloc[-1])
        vol_avg = volume.rolling(20).mean()
        result.volume_avg20 = float(vol_avg.iloc[-1]) if not pd.isna(vol_avg.iloc[-1]) else float(volume.mean())
        result.volume_ratio = result.volume / result.volume_avg20 if result.volume_avg20 > 0 else 1.0

        # Drawdown uses spec-defined 60-day window
        swing_window = min(drawdown_days, len(close))
        result.swing_high = float(close.rolling(swing_window).max().iloc[-1])
        result.drawdown_days = drawdown_days
        if result.swing_high > 0:
            result.drawdown_pct = (result.price - result.swing_high) / result.swing_high * 100

        # % distance from 200 DMA
        if result.ema200 > 0:
            result.pct_from_200dma = (result.price - result.ema200) / result.ema200 * 100

        # MACD histogram slope (avg of last 3 bars, positive = rising)
        if len(macd_hist) >= 3:
            result.macd_hist_slope = float(macd_hist.iloc[-1] - macd_hist.iloc[-3])

        if benchmark_df is not None and not benchmark_df.empty and len(benchmark_df) > 1:
            try:
                bench_close = benchmark_df["close"]
                sym_ret_20   = close.pct_change(20).iloc[-1]
                bench_ret_20 = bench_close.pct_change(20).iloc[-1]
                result.relative_strength = (1 + sym_ret_20) / (1 + bench_ret_20) if bench_ret_20 != -1 else 1.0
                # rs_diff_20: stock 20-day % return minus Nifty 20-day % return
                result.rs_diff_20 = (sym_ret_20 - bench_ret_20) * 100
            except Exception:
                result.relative_strength = 1.0
                result.rs_diff_20 = 0.0

        if vix_df is not None and not vix_df.empty:
            try:
                result.vix = float(vix_df["close"].iloc[-1])
            except Exception:
                result.vix = 15.0

    except Exception as e:
        result.error = str(e)
        logger.error(f"Indicator computation error for {symbol}: {e}")

    return result


def compute_market_breadth(symbols: list, dfs: dict) -> float:
    """Compute market breadth: fraction of symbols above their 200 EMA."""
    above = 0
    total = 0
    for sym in symbols:
        df = dfs.get(sym)
        if df is None or df.empty or len(df) < 30:
            continue
        close = df["close"]
        ema200 = float(_ema(close, min(200, len(close))).iloc[-1])
        total += 1
        if float(close.iloc[-1]) > ema200:
            above += 1
    return above / total if total > 0 else 0.5
