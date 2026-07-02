"""Unit tests for the trade engines."""
import pytest
from datetime import date
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from state_quant_engine.engine.indicators.technical import IndicatorResult
from state_quant_engine.engine.health_score_engine import HealthScoreResult
from state_quant_engine.engine.trade_engine import EntryEngine, ExitEngine, ChunkEngine
from state_quant_engine.models.orm_models import Position


def make_settings():
    from state_quant_engine.config.settings import Settings
    return Settings()


def make_health(score_pct=75.0, recommendation="BUY") -> HealthScoreResult:
    result = HealthScoreResult(symbol="TEST")
    result.score = score_pct
    result.max_score = 100.0
    result.recommendation = recommendation
    return result


def make_indicator(price=100.0, vix=15.0, macd_line=1.0, macd_signal=0.5) -> IndicatorResult:
    ind = IndicatorResult(symbol="TEST")
    ind.price = price
    ind.vix = vix
    ind.macd_line = macd_line
    ind.macd_signal = macd_signal
    ind.ema20 = price * 0.98
    ind.atr14 = 1.5
    return ind


def make_position(buy_price=100.0, current_profit=5.0, highest_profit=8.0) -> Position:
    pos = Position()
    pos.symbol = "TEST"
    pos.buy_price = buy_price
    pos.current_price = buy_price * (1 + current_profit / 100)
    pos.current_profit = current_profit
    pos.highest_profit = highest_profit
    pos.buy_date = date.today()
    pos.quantity = 10
    return pos


class TestEntryEngine:
    def setup_method(self):
        self.settings = make_settings()
        self.engine = EntryEngine(self.settings)

    def test_buy_signal_when_healthy(self):
        ind = make_indicator()
        health = make_health(score_pct=80.0)
        signal = self.engine.evaluate(ind, health, 0, 500000, "STOCK")
        assert signal.action == "BUY"

    def test_wait_when_low_health(self):
        ind = make_indicator()
        health = make_health(score_pct=40.0, recommendation="WATCH")
        signal = self.engine.evaluate(ind, health, 0, 500000, "STOCK")
        assert signal.action == "WAIT"

    def test_no_trade_high_vix(self):
        ind = make_indicator(vix=30.0)
        health = make_health(score_pct=80.0)
        signal = self.engine.evaluate(ind, health, 0, 500000, "STOCK")
        assert signal.action == "NO_TRADE"

    def test_hold_when_all_chunks_deployed(self):
        ind = make_indicator()
        health = make_health(score_pct=80.0)
        settings = make_settings()
        # Pass max chunks to trigger "all deployed"
        max_chunks = settings.stock_capital.num_chunks
        signal = self.engine.evaluate(ind, health, max_chunks, 500000, "STOCK")
        assert signal.action == "HOLD"

    def test_wait_insufficient_capital(self):
        ind = make_indicator()
        health = make_health(score_pct=80.0)
        signal = self.engine.evaluate(ind, health, 0, 100, "STOCK")
        assert signal.action == "WAIT"


class TestExitEngine:
    def setup_method(self):
        self.settings = make_settings()
        self.engine = ExitEngine(self.settings)

    def test_trailing_exit_triggered(self):
        ind = make_indicator()
        health = make_health(score_pct=60.0)
        pos = make_position(current_profit=3.0, highest_profit=8.0)
        signal = self.engine.evaluate(ind, health, pos, 30)
        assert signal.action == "EXIT"

    def test_no_exit_when_healthy(self):
        ind = make_indicator()
        health = make_health(score_pct=75.0)
        pos = make_position(current_profit=5.0, highest_profit=5.0)
        signal = self.engine.evaluate(ind, health, pos, 10)
        assert signal.action == "HOLD"

    def test_momentum_exit(self):
        ind = make_indicator(macd_line=-1.0, macd_signal=0.5)
        ind.price = 95.0
        ind.ema20 = 100.0
        health = make_health(score_pct=60.0)
        pos = make_position(current_profit=1.0, highest_profit=2.0)
        signal = self.engine.evaluate(ind, health, pos, 5)
        assert signal.action == "EXIT"

    def test_health_exit(self):
        ind = make_indicator()
        health = make_health(score_pct=20.0, recommendation="EXIT")
        pos = make_position(current_profit=1.0, highest_profit=1.0)
        signal = self.engine.evaluate(ind, health, pos, 10)
        assert signal.action == "EXIT"


class TestChunkEngine:
    def setup_method(self):
        self.settings = make_settings()
        self.engine = ChunkEngine(self.settings)

    def test_next_buy_price_etf(self):
        next_price = self.engine.get_next_buy_price("ETF", 100.0, 1)
        assert next_price is not None
        assert next_price < 100.0

    def test_no_next_when_all_chunks(self):
        max_chunks = self.settings.etf_capital.num_chunks
        result = self.engine.get_next_buy_price("ETF", 100.0, max_chunks)
        assert result is None

    def test_compute_average_price(self):
        positions = [
            make_position(buy_price=100.0),
            make_position(buy_price=95.0),
        ]
        avg = self.engine.compute_average_price(positions)
        assert 95.0 < avg < 100.0
