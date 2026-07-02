"""Unit tests for the indicator engine."""
import pytest
import pandas as pd
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from state_quant_engine.engine.indicators.technical import (
    _ema, _rsi, _macd, _adx, _atr, compute_indicators, IndicatorResult
)


def make_price_series(n=200, start=100.0, trend=0.001):
    np.random.seed(42)
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + trend + np.random.randn() * 0.01))
    return pd.Series(prices)


def make_ohlcv_df(n=200):
    close = make_price_series(n)
    return pd.DataFrame({
        "open": close * 0.998,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.random.randint(100000, 1000000, n),
    })


class TestEMA:
    def test_ema_length(self):
        s = make_price_series(100)
        result = _ema(s, 20)
        assert len(result) == 100

    def test_ema_converges(self):
        s = pd.Series([100.0] * 50)
        result = _ema(s, 10)
        assert abs(float(result.iloc[-1]) - 100.0) < 0.001

    def test_ema_short_span(self):
        s = make_price_series(10)
        result = _ema(s, 5)
        assert len(result) == 10


class TestRSI:
    def test_rsi_range(self):
        s = make_price_series(100)
        rsi = _rsi(s, 14)
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_overbought_trend(self):
        # Need enough data for RSI to converge (at least 2*period)
        rising = pd.Series([float(i) for i in range(1, 60)])
        rsi = _rsi(rising, 14)
        valid = rsi.dropna()
        assert len(valid) > 0 and float(valid.iloc[-1]) > 70

    def test_rsi_oversold_trend(self):
        falling = pd.Series([float(100 - i) for i in range(50)])
        rsi = _rsi(falling, 14)
        assert float(rsi.iloc[-1]) < 30


class TestMACD:
    def test_macd_returns_three_series(self):
        s = make_price_series(100)
        ml, ms, mh = _macd(s)
        assert len(ml) == len(ms) == len(mh) == 100

    def test_macd_histogram_is_diff(self):
        s = make_price_series(100)
        ml, ms, mh = _macd(s)
        expected = ml - ms
        pd.testing.assert_series_equal(mh, expected)


class TestComputeIndicators:
    def test_valid_result(self):
        df = make_ohlcv_df(200)
        result = compute_indicators(df, "TEST")
        assert result.is_valid
        assert result.price > 0
        assert 0 <= result.rsi14 <= 100
        assert result.ema20 > 0
        assert result.ema200 > 0

    def test_insufficient_data(self):
        df = make_ohlcv_df(10)
        result = compute_indicators(df, "TEST")
        assert not result.is_valid
        assert result.error is not None

    def test_empty_df(self):
        result = compute_indicators(pd.DataFrame(), "EMPTY")
        assert not result.is_valid

    def test_volume_ratio(self):
        df = make_ohlcv_df(200)
        result = compute_indicators(df, "TEST")
        assert result.volume_ratio > 0

    def test_drawdown(self):
        df = make_ohlcv_df(200)
        result = compute_indicators(df, "TEST")
        assert result.drawdown_pct <= 0
