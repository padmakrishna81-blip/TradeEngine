"""Dual health score engine — Stock Health + Market Health (separate, independent)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
from state_quant_engine.engine.indicators.technical import IndicatorResult


# ─────────────────────────────────────────────────────────────────────────────
# Shared result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HealthScoreResult:
    """Result of a health score computation (stock OR market)."""
    symbol: str
    score: float = 0.0
    max_score: float = 100.0
    recommendation: str = "WATCH"
    reasons: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def score_pct(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0.0


@dataclass
class MarketHealthResult:
    """Result of the Market Health Score computation."""
    score_pct: float = 0.0
    deploy_pct: float = 100.0   # capital deployment multiplier (0-100)
    deploy_label: str = "Full Deploy"
    component_scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Bell-curve drawdown scorer
# ─────────────────────────────────────────────────────────────────────────────

def _bell_drawdown_score(drawdown_pct: float, weight: float) -> Tuple[float, str]:
    """
    Bell-shaped scoring for drawdown from swing high:
      0–2%   → 0   (too expensive / extended)
      2–5%   → weight × 0.5  (mild pullback)
      5–8%   → weight × 1.0  (ideal healthy pullback)
      8–12%  → weight × 0.75 (deeper but ok)
      12–15% → weight × 0.25 (caution zone)
      > 15%  → 0   (possible trend damage)
    Note: drawdown_pct is NEGATIVE (e.g. -6 means 6% below swing high).
    """
    dd = abs(drawdown_pct)   # work with positive magnitude

    if dd < 2:
        return 0.0, f"Drawdown {dd:.1f}% — too extended, no pullback"
    elif dd < 5:
        earned = weight * 0.5
        return earned, f"Drawdown {dd:.1f}% — mild pullback (50% score)"
    elif dd < 8:
        return weight, f"Drawdown {dd:.1f}% — ideal healthy pullback (full score)"
    elif dd < 12:
        earned = weight * 0.75
        return earned, f"Drawdown {dd:.1f}% — moderate pullback (75% score)"
    elif dd <= 15:
        earned = weight * 0.25
        return earned, f"Drawdown {dd:.1f}% — deep pullback, caution (25% score)"
    else:
        return 0.0, f"Drawdown {dd:.1f}% — exceeds 15%, possible trend damage"


# ─────────────────────────────────────────────────────────────────────────────
# Stock-level checkers  (6 parameters)
# ─────────────────────────────────────────────────────────────────────────────

def _stock_200dma(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.price > ind.ema200:
        return weight, f"Price ₹{ind.price:.1f} above 200 EMA ₹{ind.ema200:.1f}"
    return 0.0, f"Price ₹{ind.price:.1f} below 200 EMA ₹{ind.ema200:.1f}"


def _stock_drawdown(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    return _bell_drawdown_score(ind.drawdown_pct, weight)


def _stock_relative_strength(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.relative_strength >= threshold:
        return weight, f"RS {ind.relative_strength:.2f} ≥ {threshold:.1f} vs NIFTY (outperforming)"
    return 0.0, f"RS {ind.relative_strength:.2f} < {threshold:.1f} vs NIFTY (underperforming)"


def _stock_volume_spike(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.volume_ratio >= threshold:
        return weight, f"Volume {ind.volume_ratio:.2f}× avg (buying interest)"
    return 0.0, f"Volume {ind.volume_ratio:.2f}× avg (weak participation)"


def _stock_rsi(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.rsi14 >= threshold:
        return weight, f"RSI {ind.rsi14:.1f} ≥ {threshold:.0f} (bullish momentum)"
    return 0.0, f"RSI {ind.rsi14:.1f} < {threshold:.0f} (weak momentum)"


def _stock_macd(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.macd_line > ind.macd_signal:
        return weight, f"MACD bullish cross (line {ind.macd_line:.4f} > signal {ind.macd_signal:.4f})"
    return 0.0, f"MACD bearish (line {ind.macd_line:.4f} < signal {ind.macd_signal:.4f})"


# Legacy checkers kept for backward-compat with custom strategies
def _check_50dma(ind, threshold, weight):
    if ind.price > ind.ema50:
        return weight, f"Price {ind.price:.1f} above 50 EMA {ind.ema50:.1f}"
    return 0.0, f"Price {ind.price:.1f} below 50 EMA {ind.ema50:.1f}"


def _check_adx(ind, threshold, weight):
    if ind.adx14 >= threshold:
        return weight, f"ADX {ind.adx14:.1f} above {threshold:.0f} (trending)"
    return 0.0, f"ADX {ind.adx14:.1f} below {threshold:.0f} (ranging)"


def _check_atr(ind, threshold, weight):
    atr_pct = (ind.atr14 / ind.price * 100) if ind.price > 0 else 0
    if atr_pct < 3.0:
        return weight, f"ATR {atr_pct:.1f}% — low volatility"
    return weight * 0.5, f"ATR {atr_pct:.1f}% — elevated volatility"


_STOCK_CHECKERS = {
    "200 DMA":          _stock_200dma,
    "Drawdown":         _stock_drawdown,
    "Relative Strength": _stock_relative_strength,
    "Volume Spike":     _stock_volume_spike,
    "RSI":              _stock_rsi,
    "MACD":             _stock_macd,
    # legacy / strategy-lab extras
    "50 DMA":           _check_50dma,
    "ADX":              _check_adx,
    "ATR":              _check_atr,
}


# ─────────────────────────────────────────────────────────────────────────────
# Market-level checkers  (3 parameters)
# ─────────────────────────────────────────────────────────────────────────────

def _market_vix(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    """Score VIX: lower is better. Graduated scoring."""
    v = ind.vix
    if v <= 13:
        return weight, f"VIX {v:.1f} — very low fear, risk-on"
    elif v <= 16:
        return weight * 0.85, f"VIX {v:.1f} — calm market (85% score)"
    elif v <= 20:
        return weight * 0.65, f"VIX {v:.1f} — mild anxiety (65% score)"
    elif v <= 25:
        return weight * 0.35, f"VIX {v:.1f} — elevated fear (35% score)"
    else:
        return 0.0, f"VIX {v:.1f} — high fear, caution"


def _market_breadth(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    """Score market breadth (0-1 fraction of stocks above 200 EMA)."""
    b = ind.breadth
    if b >= 0.70:
        return weight, f"Breadth {b:.0%} — broad participation (full score)"
    elif b >= 0.55:
        return weight * 0.75, f"Breadth {b:.0%} — decent breadth (75%)"
    elif b >= 0.40:
        return weight * 0.40, f"Breadth {b:.0%} — narrow market (40%)"
    else:
        return 0.0, f"Breadth {b:.0%} — very narrow, weak internals"


def _market_nifty_200dma(ind: IndicatorResult, threshold: float, weight: float) -> Tuple[float, str]:
    if ind.price > ind.ema200:
        gap = (ind.price - ind.ema200) / ind.ema200 * 100
        return weight, f"NIFTY {gap:.1f}% above 200 EMA — uptrend intact"
    return 0.0, f"NIFTY below 200 EMA — market downtrend"


_MARKET_CHECKERS = {
    "VIX":              _market_vix,
    "Market Breadth":   _market_breadth,
    "Nifty 200 DMA":    _market_nifty_200dma,
}


# ─────────────────────────────────────────────────────────────────────────────
# Stock Health Engine
# ─────────────────────────────────────────────────────────────────────────────

class StockHealthEngine:
    """
    Scores individual stocks on 6 parameters (total 100 weight).
    Default: 200DMA(25) + Drawdown(20) + RelStr(20) + VolSpike(15) + RSI(10) + MACD(10)
    Fully configurable via DB health_parameters (type='stock').
    """

    def __init__(
        self,
        parameters: List[Dict],
        buy_threshold: float = 70,
        hold_threshold: float = 50,
        watch_threshold: float = 35,
        exit_threshold: float = 35,
    ) -> None:
        self.parameters    = parameters
        self.buy_threshold = buy_threshold
        self.hold_threshold = hold_threshold
        self.watch_threshold = watch_threshold
        self.exit_threshold  = exit_threshold

    def compute(self, ind: IndicatorResult) -> HealthScoreResult:
        result = HealthScoreResult(symbol=ind.symbol)
        if not ind.is_valid:
            result.recommendation = "ERROR"
            result.reasons.append(ind.error or "Invalid indicator data")
            return result

        total, max_score = 0.0, 0.0
        for param in self.parameters:
            name      = param.get("parameter_name") or param.get("name", "")
            weight    = float(param.get("weight", 0))
            enabled   = param.get("enabled", True)
            threshold = float(param.get("threshold", 0))
            if not enabled or weight <= 0:
                continue
            max_score += weight
            checker = _STOCK_CHECKERS.get(name)
            if checker:
                earned, reason = checker(ind, threshold, weight)
                total += earned
                result.component_scores[name] = earned
                result.reasons.append(reason)
            else:
                result.component_scores[name] = 0.0

        result.score     = total
        result.max_score = max_score
        pct = result.score_pct
        if pct >= self.buy_threshold:
            result.recommendation = "BUY"
        elif pct >= self.hold_threshold:
            result.recommendation = "HOLD"
        elif pct >= self.exit_threshold:
            result.recommendation = "WATCH"
        else:
            result.recommendation = "EXIT"
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Market Health Engine
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_MARKET_PARAMS = [
    {"name": "VIX",            "weight": 40, "enabled": True, "threshold": 20},
    {"name": "Market Breadth", "weight": 40, "enabled": True, "threshold": 0.5},
    {"name": "Nifty 200 DMA",  "weight": 20, "enabled": True, "threshold": 0},
]

_DEFAULT_DEPLOY_TIERS = [
    {"min": 80, "deploy_pct": 100, "label": "Full Deploy"},
    {"min": 60, "deploy_pct": 75,  "label": "75% Deploy"},
    {"min": 40, "deploy_pct": 50,  "label": "50% Deploy"},
    {"min":  0, "deploy_pct": 25,  "label": "25% / Hold Cash"},
]


class MarketHealthEngine:
    """
    Scores market conditions on 3 parameters (total 100 weight).
    Default: VIX(40) + Breadth(40) + Nifty200DMA(20)
    Output: market score + capital deployment multiplier.
    """

    def __init__(
        self,
        parameters: List[Dict] = None,
        deploy_tiers: List[Dict] = None,
    ) -> None:
        self.parameters   = parameters or _DEFAULT_MARKET_PARAMS
        self.deploy_tiers = deploy_tiers or _DEFAULT_DEPLOY_TIERS

    def compute(self, nifty_ind: IndicatorResult) -> MarketHealthResult:
        """
        nifty_ind: IndicatorResult computed from NIFTY 50 (^NSEI).
        The vix and breadth fields must be pre-populated on this object.
        """
        result = MarketHealthResult()
        total, max_score = 0.0, 0.0

        for param in self.parameters:
            name      = param.get("parameter_name") or param.get("name", "")
            weight    = float(param.get("weight", 0))
            enabled   = param.get("enabled", True)
            threshold = float(param.get("threshold", 0))
            if not enabled or weight <= 0:
                continue
            max_score += weight
            checker = _MARKET_CHECKERS.get(name)
            if checker:
                earned, reason = checker(nifty_ind, threshold, weight)
                total += earned
                result.component_scores[name] = earned
                result.reasons.append(reason)

        score_pct = (total / max_score * 100) if max_score > 0 else 0.0
        result.score_pct = score_pct

        for tier in sorted(self.deploy_tiers, key=lambda t: t["min"], reverse=True):
            if score_pct >= tier["min"]:
                result.deploy_pct   = float(tier["deploy_pct"])
                result.deploy_label = tier["label"]
                break

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat alias (Strategy Lab and old code used HealthScoreEngine)
# ─────────────────────────────────────────────────────────────────────────────

class HealthScoreEngine(StockHealthEngine):
    """Alias for backward compatibility."""
    pass
