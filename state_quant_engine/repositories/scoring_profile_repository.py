"""Repository for ScoringProfile and ProfileParameter models."""
from __future__ import annotations
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from state_quant_engine.models.orm_models import ScoringProfile, ProfileParameter
from state_quant_engine.repositories.base_repository import BaseRepository

# Built-in profile name constants
PROFILE_STOCK_ENTRY = "stock_entry"
PROFILE_STOCK_HOLD  = "stock_hold"
PROFILE_ETF_ENTRY   = "etf_entry"
PROFILE_ETF_HOLD    = "etf_hold"


def profile_name(asset_type: str, context: str) -> str:
    """Return the canonical profile name for an asset_type + context."""
    a = "etf" if asset_type.upper() == "ETF" else "stock"
    c = "entry" if context == "entry" else "hold"
    return f"{a}_{c}"


class ScoringProfileRepository(BaseRepository[ScoringProfile]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ScoringProfile)

    def get_by_name(self, name: str) -> Optional[ScoringProfile]:
        return (
            self._session.query(ScoringProfile)
            .filter(ScoringProfile.name == name)
            .first()
        )

    def get_for(self, asset_type: str, context: str) -> Optional[ScoringProfile]:
        """Return the profile for a given asset type and context."""
        name = profile_name(asset_type, context)
        return self.get_by_name(name)

    def get_all_ordered(self) -> List[ScoringProfile]:
        return (
            self._session.query(ScoringProfile)
            .order_by(ScoringProfile.asset_type, ScoringProfile.context)
            .all()
        )

    def get_parameters_as_dicts(self, profile_id: int) -> List[Dict]:
        """Return enabled parameters for a profile as plain dicts for the engines."""
        rows = (
            self._session.query(ProfileParameter)
            .filter(
                ProfileParameter.profile_id == profile_id,
                ProfileParameter.enabled == True,
            )
            .all()
        )
        return [
            {
                "parameter_name": p.parameter_name,
                "weight": p.weight,
                "enabled": p.enabled,
                "threshold": p.threshold,
            }
            for p in rows
        ]

    def upsert_profile(
        self, name: str, asset_type: str, context: str,
        description: str = "",
        benchmark: str = "^NSEI",
        buy_threshold: float = 75.0,
        exit_threshold: float = 45.0,
        avg_threshold: float = 60.0,
        hard_gate_above_200dma: bool = True,
        hard_gate_no_bear_macd: bool = True,
        hard_gate_max_drawdown: float = -15.0,
        is_default: bool = False,
    ) -> ScoringProfile:
        existing = self.get_by_name(name)
        if existing:
            existing.description          = description
            existing.benchmark            = benchmark
            existing.buy_threshold        = buy_threshold
            existing.exit_threshold       = exit_threshold
            existing.avg_threshold        = avg_threshold
            existing.hard_gate_above_200dma = hard_gate_above_200dma
            existing.hard_gate_no_bear_macd = hard_gate_no_bear_macd
            existing.hard_gate_max_drawdown = hard_gate_max_drawdown
            existing.is_default           = is_default
            self._session.commit()
            return existing
        profile = ScoringProfile(
            name=name, asset_type=asset_type, context=context,
            description=description, benchmark=benchmark,
            buy_threshold=buy_threshold, exit_threshold=exit_threshold,
            avg_threshold=avg_threshold,
            hard_gate_above_200dma=hard_gate_above_200dma,
            hard_gate_no_bear_macd=hard_gate_no_bear_macd,
            hard_gate_max_drawdown=hard_gate_max_drawdown,
            is_default=is_default,
        )
        return self.add(profile)

    def upsert_parameter(
        self, profile_id: int, parameter_name: str,
        weight: float, enabled: bool = True,
        threshold: float = 0.0, description: str = "",
    ) -> ProfileParameter:
        existing = (
            self._session.query(ProfileParameter)
            .filter(
                ProfileParameter.profile_id == profile_id,
                ProfileParameter.parameter_name == parameter_name,
            )
            .first()
        )
        if existing:
            existing.weight      = weight
            existing.enabled     = enabled
            existing.threshold   = threshold
            existing.description = description
            self._session.commit()
            return existing
        p = ProfileParameter(
            profile_id=profile_id, parameter_name=parameter_name,
            weight=weight, enabled=enabled, threshold=threshold,
            description=description,
        )
        self._session.add(p)
        self._session.commit()
        return p
