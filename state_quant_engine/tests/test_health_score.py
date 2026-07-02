"""Unit tests for the health score engine."""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from state_quant_engine.engine.indicators.technical import IndicatorResult
from state_quant_engine.engine.health_score_engine import HealthScoreEngine, HealthScoreResult


DEFAULT_PARAMS = [
    {"parameter_name": "200 DMA", "weight": 20, "enabled": True, "threshold": 0},
    {"parameter_name": "50 DMA", "weight": 10, "enabled": True, "threshold": 0},
    {"parameter_name": "RSI", "weight": 15, "enabled": True, "threshold": 50},
    {"parameter_name": "MACD", "weight": 10, "enabled": True, "threshold": 0},
    {"parameter_name": "ADX", "weight": 10, "enabled": True, "threshold": 20},
    {"parameter_name": "Volume Spike", "weight": 5, "enabled": True, "threshold": 1.5},
    {"parameter_name": "Relative Strength", "weight": 10, "enabled": True, "threshold": 1.0},
    {"parameter_name": "Drawdown", "weight": 10, "enabled": True, "threshold": -15},
    {"parameter_name": "VIX", "weight": 5, "enabled": True, "threshold": 20},
    {"parameter_name": "Breadth", "weight": 10, "enabled": True, "threshold": 0.5},
]


def make_bullish_indicator(symbol="TEST") -> IndicatorResult:
    ind = IndicatorResult(symbol=symbol)
    ind.price = 200.0
    ind.ema20 = 195.0
    ind.ema50 = 190.0
    ind.ema200 = 180.0
    ind.rsi14 = 62.0
    ind.macd_line = 1.5
    ind.macd_signal = 0.8
    ind.adx14 = 28.0
    ind.atr14 = 3.0
    ind.volume = 1500000
    ind.volume_avg20 = 1000000
    ind.volume_ratio = 1.5
    ind.drawdown_pct = -5.0
    ind.relative_strength = 1.1
    ind.vix = 14.0
    ind.breadth = 0.65
    return ind


def make_bearish_indicator(symbol="TEST") -> IndicatorResult:
    ind = IndicatorResult(symbol=symbol)
    ind.price = 80.0
    ind.ema20 = 90.0
    ind.ema50 = 95.0
    ind.ema200 = 100.0
    ind.rsi14 = 38.0
    ind.macd_line = -1.5
    ind.macd_signal = -0.5
    ind.adx14 = 12.0
    ind.atr14 = 5.0
    ind.volume = 500000
    ind.volume_avg20 = 1000000
    ind.volume_ratio = 0.5
    ind.drawdown_pct = -25.0
    ind.relative_strength = 0.85
    ind.vix = 28.0
    ind.breadth = 0.35
    return ind


class TestHealthScoreEngine:
    def setup_method(self):
        self.engine = HealthScoreEngine(DEFAULT_PARAMS)

    def test_bullish_signal(self):
        result = self.engine.compute(make_bullish_indicator())
        assert result.recommendation in ("BUY", "HOLD")
        assert result.score_pct >= 50

    def test_bearish_signal(self):
        result = self.engine.compute(make_bearish_indicator())
        assert result.recommendation in ("EXIT", "WATCH")
        assert result.score_pct < 50

    def test_invalid_indicator(self):
        ind = IndicatorResult(symbol="BAD", error="fetch error")
        result = self.engine.compute(ind)
        assert result.recommendation == "ERROR"

    def test_score_within_range(self):
        result = self.engine.compute(make_bullish_indicator())
        assert 0 <= result.score_pct <= 100

    def test_component_scores_present(self):
        result = self.engine.compute(make_bullish_indicator())
        assert len(result.component_scores) > 0

    def test_disabled_param_ignored(self):
        params_with_disabled = [
            {"parameter_name": "200 DMA", "weight": 20, "enabled": False, "threshold": 0},
            {"parameter_name": "RSI", "weight": 15, "enabled": True, "threshold": 50},
        ]
        engine = HealthScoreEngine(params_with_disabled)
        result = engine.compute(make_bullish_indicator())
        assert "200 DMA" not in result.component_scores or result.component_scores.get("200 DMA", 0) == 0

    def test_thresholds_respected(self):
        # With only RSI passing (score=15/105 ~14%), EXIT is correct behavior at low buy threshold
        # Test that a higher score with lower threshold gives BUY
        engine_low = HealthScoreEngine(DEFAULT_PARAMS, buy_threshold=10)
        ind = make_bearish_indicator()
        ind.rsi14 = 55  # RSI passes (weight=15), score_pct ~14% > buy_threshold 10%
        result = engine_low.compute(ind)
        assert result.recommendation in ("BUY", "HOLD")


class TestHealthScoreResult:
    def test_score_pct_zero_max(self):
        result = HealthScoreResult(symbol="TEST", score=0, max_score=0)
        assert result.score_pct == 0.0

    def test_score_pct_calculation(self):
        result = HealthScoreResult(symbol="TEST", score=70, max_score=100)
        assert result.score_pct == 70.0
