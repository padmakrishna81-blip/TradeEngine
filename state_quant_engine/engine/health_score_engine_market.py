"""Market Health Engine — VIX + Breadth + Nifty 200 DMA → deploy multiplier."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from state_quant_engine.engine.indicators.technical import IndicatorResult


@dataclass
class MarketHealthResult:
    score_pct: float = 0.0
    deploy_pct: float = 100.0
    deploy_label: str = "Full Deploy"
    component_scores: Dict[str, float] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


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


def _market_vix(ind: IndicatorResult, weight: float) -> tuple[float, str]:
    v = ind.vix
    if v <= 13:   return weight,        f"VIX {v:.1f} — very low fear, risk-on"
    if v <= 16:   return weight * 0.85, f"VIX {v:.1f} — calm (85%)"
    if v <= 20:   return weight * 0.65, f"VIX {v:.1f} — mild anxiety (65%)"
    if v <= 25:   return weight * 0.35, f"VIX {v:.1f} — elevated fear (35%)"
    return 0.0,                         f"VIX {v:.1f} — high fear, caution"


def _market_breadth(ind: IndicatorResult, weight: float) -> tuple[float, str]:
    b = ind.breadth
    if b >= 0.70: return weight,        f"Breadth {b:.0%} — broad participation"
    if b >= 0.55: return weight * 0.75, f"Breadth {b:.0%} — decent (75%)"
    if b >= 0.40: return weight * 0.40, f"Breadth {b:.0%} — narrow (40%)"
    return 0.0,                         f"Breadth {b:.0%} — very narrow"


def _market_nifty200(ind: IndicatorResult, weight: float) -> tuple[float, str]:
    if ind.price > ind.ema200:
        gap = (ind.price - ind.ema200) / ind.ema200 * 100
        return weight, f"NIFTY {gap:.1f}% above 200 EMA — uptrend"
    return 0.0, "NIFTY below 200 EMA — downtrend"


_CHECKERS = {"VIX": _market_vix, "Market Breadth": _market_breadth, "Nifty 200 DMA": _market_nifty200}


class MarketHealthEngine:
    def __init__(self, parameters=None, deploy_tiers=None):
        self.parameters   = parameters or _DEFAULT_MARKET_PARAMS
        self.deploy_tiers = deploy_tiers or _DEFAULT_DEPLOY_TIERS

    def compute(self, nifty_ind: IndicatorResult) -> MarketHealthResult:
        result = MarketHealthResult()
        total, max_w = 0.0, 0.0
        for p in self.parameters:
            name    = p.get("parameter_name") or p.get("name", "")
            weight  = float(p.get("weight", 0))
            enabled = p.get("enabled", True)
            if not enabled or weight <= 0:
                continue
            max_w += weight
            fn = _CHECKERS.get(name)
            if fn:
                earned, reason = fn(nifty_ind, weight)
                total += earned
                result.component_scores[name] = earned
                result.reasons.append(reason)

        result.score_pct = (total / max_w * 100) if max_w > 0 else 0.0
        for tier in sorted(self.deploy_tiers, key=lambda t: t["min"], reverse=True):
            if result.score_pct >= tier["min"]:
                result.deploy_pct   = float(tier["deploy_pct"])
                result.deploy_label = tier["label"]
                break
        return result
