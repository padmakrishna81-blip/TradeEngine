"""Market data fetcher with caching."""
from __future__ import annotations
import time
from typing import Dict, Optional, Tuple
import pandas as pd
import yfinance as yf
from loguru import logger


class DataCache:
    """Simple in-memory TTL cache for OHLCV data."""

    def __init__(self, ttl_seconds: int = 900) -> None:
        self._cache: Dict[str, Tuple[pd.DataFrame, float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[pd.DataFrame]:
        if key in self._cache:
            df, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                return df
            del self._cache[key]
        return None

    def set(self, key: str, df: pd.DataFrame) -> None:
        self._cache[key] = (df, time.time())

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


_cache = DataCache()
# Short TTL cache for live prices (60 seconds)
_price_cache: Dict[str, Tuple[float, float, float, float]] = {}  # symbol → (cmp, prev_close, change_pct, ts)
_PRICE_TTL = 60


def fetch_ohlcv(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
    ttl_seconds: int = 900,
) -> pd.DataFrame:
    """Fetch OHLCV data for a symbol, using cache."""
    cache_key = f"{symbol}:{period}:{interval}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning(f"No data returned for {symbol}")
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        df.columns = [c.lower() for c in df.columns]
        _cache.set(cache_key, df)
        return df
    except Exception as e:
        logger.error(f"Failed to fetch data for {symbol}: {e}")
        return pd.DataFrame()


def fetch_price_with_change(symbol: str) -> tuple[float, float, float]:
    """
    Return (cmp, prev_close, change_pct) for a symbol.

    cmp         — current market price (real-time / 15-min delayed)
    prev_close  — previous trading session close
    change_pct  — (cmp - prev_close) / prev_close × 100

    Cached for 60 seconds.
    """
    now = time.time()
    if symbol in _price_cache:
        cmp, prev, chg, ts = _price_cache[symbol]
        if now - ts < _PRICE_TTL:
            return cmp, prev, chg

    cmp, prev_close = 0.0, 0.0
    try:
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info

        lp = getattr(fi, "last_price", None)
        if lp and lp > 0:
            cmp = float(lp)

        pc = getattr(fi, "previous_close", None)
        if pc and pc > 0:
            prev_close = float(pc)

        # If market closed, last_price == previous_close; fall back to day before
        if cmp == 0.0 and prev_close > 0:
            cmp = prev_close

    except Exception as e:
        logger.warning(f"fast_info failed for {symbol}: {e}")

    # Final fallback via OHLCV history
    if cmp == 0.0 or prev_close == 0.0:
        df = fetch_ohlcv(symbol)
        if not df.empty and len(df) >= 2:
            if cmp == 0.0:
                cmp = float(df["close"].iloc[-1])
            if prev_close == 0.0:
                prev_close = float(df["close"].iloc[-2])

    change_pct = (cmp - prev_close) / prev_close * 100 if prev_close > 0 else 0.0

    if cmp > 0:
        _price_cache[symbol] = (cmp, prev_close, change_pct, now)

    return cmp, prev_close, change_pct


def fetch_current_price(symbol: str) -> float:
    """Fetch just the current market price (wrapper around fetch_price_with_change)."""
    cmp, _, _ = fetch_price_with_change(symbol)
    return cmp


def get_cache() -> DataCache:
    return _cache


def fetch_current_price(symbol: str) -> float:
    """
    Fetch the latest market price for a symbol.

    Priority:
    1. fast_info.last_price  — real-time/delayed quote (intraday accurate)
    2. fast_info.previous_close — previous session close if market is closed
    3. history last close    — fallback when fast_info is unavailable

    Result is cached for 60 seconds to avoid hammering the API.
    """
    now = time.time()
    if symbol in _price_cache:
        price, ts = _price_cache[symbol]
        if now - ts < _PRICE_TTL:
            return price

    price = 0.0
    try:
        ticker = yf.Ticker(symbol)
        fi = ticker.fast_info

        # Try live price first
        lp = getattr(fi, "last_price", None)
        if lp and lp > 0:
            price = float(lp)
        else:
            # Fall back to previous close
            pc = getattr(fi, "previous_close", None)
            if pc and pc > 0:
                price = float(pc)

    except Exception as e:
        logger.warning(f"fast_info failed for {symbol}: {e}")

    # Final fallback: last row of OHLCV history
def get_cache() -> DataCache:
    return _cache
