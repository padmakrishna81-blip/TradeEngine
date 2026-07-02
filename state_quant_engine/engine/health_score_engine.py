"""
Dual health score engines:
  EntryHealthEngine  — for scanner, decides BUY / WAIT on fresh positions
  HoldHealthEngine   — for portfolio, feeds EXIT / AVG / HOLD decision

Both use the same 6 parameters with different contribution rules per spec.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any
from state_quant_engine.engine.indicators.technical import IndicatorResult


# ─────────────────────────────────────────────────────────────────────────────
# Shared result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HealthScoreResult:
    symbol: str
    score: float = 0.0
    max_score: float = 100.0
    recommendation: str = "WAIT"
    reasons: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)
    contributions: Dict[str, float] = field(default_factory=dict)  # 0.0–1.0 per param

    @property
    def score_pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Entry contribution functions  (spec §6.1)
# ─────────────────────────────────────────────────────────────────────────────

def _entry_200dma(ind: IndicatorResult) -> tuple[float, str]:
    p = ind.pct_from_200dma
    if p >= 8:    return 1.00, f"200DMA: +{p:.1f}% above (strong trend)"
    if p >= 4:    return 0.85, f"200DMA: +{p:.1f}% above (good)"
    if p >= 0:    return 0.65, f"200DMA: +{p:.1f}% above (marginal)"
    if p >= -3:   return 0.25, f"200DMA: {p:.1f}% below (weak)"
    return 0.00,               f"200DMA: {p:.1f}% below (broken)"


def _entry_drawdown(ind: IndicatorResult) -> tuple[float, str]:
    d = ind.drawdown_pct   # negative
    if d >= -2:   return 0.20, f"Drawdown {d:.1f}%: near highs, wait for pullback"
    if d >= -5:   return 0.70, f"Drawdown {d:.1f}%: mild pullback"
    if d >= -8:   return 1.00, f"Drawdown {d:.1f}%: ideal healthy pullback ✓"
    if d >= -12:  return 0.75, f"Drawdown {d:.1f}%: moderate pullback"
    if d >= -15:  return 0.35, f"Drawdown {d:.1f}%: deep pullback, caution"
    return 0.00,               f"Drawdown {d:.1f}%: excessive, possible breakdown"


def _entry_rs(ind: IndicatorResult) -> tuple[float, str]:
    r = ind.rs_diff_20
    if r >= 5:    return 1.00, f"RS: +{r:.1f}% vs Nifty (strong leader)"
    if r >= 2:    return 0.80, f"RS: +{r:.1f}% vs Nifty (outperforming)"
    if r >= 0:    return 0.60, f"RS: {r:.1f}% vs Nifty (in-line)"
    if r >= -2:   return 0.25, f"RS: {r:.1f}% vs Nifty (lagging)"
    return 0.00,               f"RS: {r:.1f}% vs Nifty (underperforming)"


def _entry_volume(ind: IndicatorResult) -> tuple[float, str]:
    v = ind.volume_ratio
    if v >= 2.0:  return 1.00, f"Volume {v:.2f}x avg (strong interest)"
    if v >= 1.5:  return 0.85, f"Volume {v:.2f}x avg (above avg)"
    if v >= 1.2:  return 0.65, f"Volume {v:.2f}x avg (moderate)"
    if v >= 1.0:  return 0.35, f"Volume {v:.2f}x avg (light)"
    return 0.00,               f"Volume {v:.2f}x avg (below avg)"


def _entry_rsi(ind: IndicatorResult) -> tuple[float, str]:
    r = ind.rsi14
    if 48 <= r <= 60: return 1.00, f"RSI {r:.1f}: ideal bullish recovery zone"
    if 40 <= r < 48:  return 0.85, f"RSI {r:.1f}: recovering from oversold"
    if 60 < r <= 68:  return 0.70, f"RSI {r:.1f}: bullish but extended"
    if 35 <= r < 40:  return 0.55, f"RSI {r:.1f}: oversold, watch for turn"
    if 68 < r <= 75:  return 0.35, f"RSI {r:.1f}: overbought zone"
    if r < 35:        return 0.15, f"RSI {r:.1f}: deep oversold"
    return 0.10,                   f"RSI {r:.1f}: extreme overbought"


def _entry_macd(ind: IndicatorResult) -> tuple[float, str]:
    above = ind.macd_line > ind.macd_signal
    slope = ind.macd_hist_slope
    near_cross = abs(ind.macd_line - ind.macd_signal) < abs(ind.macd_line) * 0.1 + 0.0001

    if above and slope > 0:
        return 1.00, "MACD: bullish and histogram rising"
    if above and slope >= 0:
        return 0.75, "MACD: bullish, histogram flat"
    if near_cross and not above:
        return 0.55, "MACD: near bullish crossover"
    if not above and slope > 0:
        return 0.25, "MACD: below signal but improving"
    return 0.00, "MACD: bearish and weakening"


# ─────────────────────────────────────────────────────────────────────────────
# Hold contribution functions  (spec §9)
# ─────────────────────────────────────────────────────────────────────────────

def _hold_200dma(ind: IndicatorResult) -> tuple[float, str]:
    p = ind.pct_from_200dma
    if p >= 5:    return 1.00, f"200DMA: +{p:.1f}% (healthy uptrend)"
    if p >= 0:    return 0.85, f"200DMA: +{p:.1f}% (still above)"
    if p >= -3:   return 0.55, f"200DMA: {p:.1f}% (just below, watch)"
    if p >= -5:   return 0.25, f"200DMA: {p:.1f}% (weakening)"
    return 0.00,               f"200DMA: {p:.1f}% (broken, below support)"


def _hold_drawdown(ind: IndicatorResult) -> tuple[float, str]:
    d = ind.drawdown_pct
    if d >= -4:   return 1.00, f"Drawdown {d:.1f}%: near highs, position healthy"
    if d >= -8:   return 0.80, f"Drawdown {d:.1f}%: moderate pullback"
    if d >= -12:  return 0.55, f"Drawdown {d:.1f}%: deeper decline"
    if d >= -15:  return 0.25, f"Drawdown {d:.1f}%: significant decline"
    return 0.00,               f"Drawdown {d:.1f}%: critical — possible breakdown"


def _hold_rs(ind: IndicatorResult) -> tuple[float, str]:
    r = ind.rs_diff_20
    if r >= 3:    return 1.00, f"RS: +{r:.1f}% vs Nifty (outperforming)"
    if r >= 0:    return 0.75, f"RS: {r:.1f}% vs Nifty (in-line)"
    if r >= -2:   return 0.50, f"RS: {r:.1f}% vs Nifty (slight lag)"
    if r >= -5:   return 0.20, f"RS: {r:.1f}% vs Nifty (lagging)"
    return 0.00,               f"RS: {r:.1f}% vs Nifty (significantly underperforming)"


def _hold_volume(ind: IndicatorResult) -> tuple[float, str]:
    v = ind.volume_ratio
    if v >= 1.2:  return 1.00, f"Volume {v:.2f}x avg"
    if v >= 1.0:  return 0.75, f"Volume {v:.2f}x avg (normal)"
    if v >= 0.8:  return 0.50, f"Volume {v:.2f}x avg (below normal)"
    if v >= 0.6:  return 0.25, f"Volume {v:.2f}x avg (low)"
    return 0.00,               f"Volume {v:.2f}x avg (very thin)"


def _hold_rsi(ind: IndicatorResult) -> tuple[float, str]:
    r = ind.rsi14
    if 45 <= r <= 70: return 1.00, f"RSI {r:.1f}: healthy hold zone"
    if 40 <= r < 45:  return 0.75, f"RSI {r:.1f}: weakening momentum"
    if 35 <= r < 40:  return 0.50, f"RSI {r:.1f}: oversold territory"
    if 30 <= r < 35:  return 0.20, f"RSI {r:.1f}: deeply oversold"
    return 0.00,                   f"RSI {r:.1f}: extreme weakness"


def _hold_macd(ind: IndicatorResult) -> tuple[float, str]:
    above = ind.macd_line > ind.macd_signal
    slope = ind.macd_hist_slope
    if above and slope >= 0:
        return 1.00, "MACD: bullish, histogram stable/rising"
    if above and slope < 0:
        return 0.75, "MACD: bullish but histogram weakening"
    near_cross = abs(ind.macd_line - ind.macd_signal) < abs(ind.macd_line) * 0.1 + 0.0001
    if near_cross:
        return 0.50, "MACD: near crossover"
    if not above and slope > 0:
        return 0.25, "MACD: below signal, mild weakness"
    return 0.00, "MACD: bearish, histogram falling"


def _hold_profit(ind: IndicatorResult, threshold: float, profit_pct: float = 0.0) -> tuple[float, str]:
    """
    Profit % contribution for hold health.
    threshold = profit % at which contribution reaches 1.0.
    Below 0%  → 0.0 (loss hurts hold health)
    0-threshold → linear ramp 0→1.0
    Above threshold → 1.0 (but high profit combined with weak other params → exit)
    """
    if profit_pct < 0:
        # Loss — scale penalty 0 at 0% to 0 at -threshold (clamp)
        return max(0.0, 1.0 + profit_pct / threshold) if threshold > 0 else 0.0, \
               f"Profit {profit_pct:.1f}%: in loss (reduces hold score)"
    contribution = min(profit_pct / threshold, 1.0) if threshold > 0 else 0.0
    label = (f"Profit {profit_pct:.1f}% ≥ {threshold:.0f}% target"
             if profit_pct >= threshold
             else f"Profit {profit_pct:.1f}% / {threshold:.0f}% target ({contribution*100:.0f}%)")
    return contribution, label


# Maps param name → (entry_fn, hold_fn)
_ENTRY_FNS = {
    "200 DMA":           _entry_200dma,
    "Drawdown":          _entry_drawdown,
    "Relative Strength": _entry_rs,
    "Volume Spike":      _entry_volume,
    "RSI":               _entry_rsi,
    "MACD":              _entry_macd,
}
_HOLD_FNS = {
    "200 DMA":           _hold_200dma,
    "Drawdown":          _hold_drawdown,
    "Relative Strength": _hold_rs,
    "Volume Spike":      _hold_volume,
    "RSI":               _hold_rsi,
    "MACD":              _hold_macd,
    "Profit %":          None,   # handled specially — needs profit_pct arg
}

# Default weights per spec §6 / §8
_DEFAULT_WEIGHTS = {
    "200 DMA":           25,
    "Drawdown":          20,
    "Relative Strength": 20,
    "Volume Spike":      10,
    "RSI":               15,
    "MACD":              10,
}


def _compute_health(ind: IndicatorResult, fn_map: dict, params: List[Dict],
                    profit_pct: float = 0.0) -> HealthScoreResult:
    result = HealthScoreResult(symbol=ind.symbol)
    if not ind.is_valid:
        result.recommendation = "ERROR"
        result.reasons.append(ind.error or "Invalid data")
        return result

    total_weight = 0.0
    weighted_sum = 0.0

    for param in params:
        name      = param.get("parameter_name") or param.get("name", "")
        weight    = float(param.get("weight", _DEFAULT_WEIGHTS.get(name, 0)))
        enabled   = param.get("enabled", True)
        threshold = float(param.get("threshold", 0))
        if not enabled or weight <= 0:
            continue

        if name == "Profit %":
            contribution, reason = _hold_profit(ind, threshold, profit_pct)
        else:
            fn = fn_map.get(name)
            if not fn:
                continue
            contribution, reason = fn(ind)

        total_weight += weight
        weighted_sum += weight * contribution
        result.contributions[name] = contribution
        result.component_scores[name] = round(weight * contribution, 2)
        result.reasons.append(reason)

    result.max_score = total_weight
    result.score     = weighted_sum
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public engines
# ─────────────────────────────────────────────────────────────────────────────

class EntryHealthEngine:
    """Computes Entry Health % and BUY/WAIT signal for scanner (fresh entries only)."""

    BUY_THRESHOLD = 75.0

    def __init__(self, parameters: List[Dict], buy_threshold: float = BUY_THRESHOLD,
                 hard_gate_above_200dma: bool = True,
                 hard_gate_no_strong_bear_macd: bool = True,
                 hard_gate_max_drawdown: float = -15.0, **_):
        self.parameters                 = parameters
        self.buy_threshold              = buy_threshold
        self.hard_gate_above_200dma     = hard_gate_above_200dma
        self.hard_gate_no_strong_bear   = hard_gate_no_strong_bear_macd
        self.hard_gate_max_drawdown     = hard_gate_max_drawdown

    def compute(self, ind: IndicatorResult) -> HealthScoreResult:
        result = _compute_health(ind, _ENTRY_FNS, self.parameters)

        # Hard gates — each is independently configurable
        hard_gate_fail = None
        if self.hard_gate_above_200dma and ind.price < ind.ema200:
            hard_gate_fail = f"Hard gate: price ₹{ind.price:.2f} below 200 DMA ₹{ind.ema200:.2f}"
        elif self.hard_gate_no_strong_bear and ind.macd_line < ind.macd_signal and ind.macd_hist_slope < 0:
            hard_gate_fail = "Hard gate: MACD strong bearish"
        elif ind.drawdown_pct < self.hard_gate_max_drawdown:
            hard_gate_fail = f"Hard gate: drawdown {ind.drawdown_pct:.1f}% < {self.hard_gate_max_drawdown:.0f}%"

        if hard_gate_fail:
            result.recommendation = "WAIT"
            result.reasons.insert(0, hard_gate_fail)
        elif result.score_pct >= self.buy_threshold:
            result.recommendation = "BUY"
        else:
            result.recommendation = "WAIT"

        return result


class HoldHealthEngine:
    """Computes Hold Health % for portfolio (existing positions only)."""

    def __init__(self, parameters: List[Dict], **_):
        self.parameters = parameters

    def compute(self, ind: IndicatorResult, profit_pct: float = 0.0) -> HealthScoreResult:
        result = _compute_health(ind, _HOLD_FNS, self.parameters, profit_pct=profit_pct)
        result.recommendation = "HOLD"
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat aliases
# ─────────────────────────────────────────────────────────────────────────────

class StockHealthEngine(EntryHealthEngine):
    pass

class HealthScoreEngine(EntryHealthEngine):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Market Health Engine (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

from state_quant_engine.engine.health_score_engine_market import (  # noqa: E402
    MarketHealthEngine, MarketHealthResult,
    _DEFAULT_MARKET_PARAMS, _DEFAULT_DEPLOY_TIERS,
)
