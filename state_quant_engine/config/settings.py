"""Settings loader from YAML config."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import yaml

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class AppConfig:
    name: str = "STATE Quant Engine"
    version: str = "1.0.0"
    theme: str = "dark"


@dataclass
class MarketConfig:
    open_time: str = "09:15"
    close_time: str = "15:30"
    timezone: str = "Asia/Kolkata"


@dataclass
class DataConfig:
    cache_ttl_minutes: int = 15
    download_period: str = "1y"
    download_interval: str = "1d"
    drawdown_days: int = 52


@dataclass
class DatabaseConfig:
    path: str = "data/sqe.db"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    rotation: str = "1 day"
    retention: str = "30 days"
    path: str = "logs/sqe.log"


@dataclass
class CapitalConfig:
    total: float = 2000000
    num_chunks: int = 5
    chunk_percentages: List[float] = field(default_factory=lambda: [20, 20, 20, 20, 20])
    next_buy_triggers: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 2.0, 3.0])
    max_per_stock: Optional[float] = None
    num_stocks: Optional[int] = None
    num_chunks_stock: int = 3
    chunk_percentages_stock: List[float] = field(default_factory=lambda: [35, 35, 30])


@dataclass
class HealthScoreThresholds:
    buy_threshold: float = 70
    hold_threshold: float = 50
    watch_threshold: float = 35
    exit_threshold: float = 35


@dataclass
class ProfitManagementConfig:
    profit_threshold: float = 3.0
    partial_exit_threshold: float = 3.0
    full_exit_threshold: float = 3.0
    strong_hold_health_min: float = 70
    strong_hold_trend: str = "Bullish"


@dataclass
class Settings:
    """Application settings loaded from YAML."""

    app: AppConfig = field(default_factory=AppConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    data: DataConfig = field(default_factory=DataConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    etf_capital: CapitalConfig = field(default_factory=CapitalConfig)
    stock_capital: CapitalConfig = field(default_factory=CapitalConfig)
    health_scores: HealthScoreThresholds = field(default_factory=HealthScoreThresholds)
    profit_management: ProfitManagementConfig = field(default_factory=ProfitManagementConfig)
    health_parameters: List[Dict[str, Any]] = field(default_factory=list)          # legacy / strategy-lab
    stock_health_parameters: List[Dict[str, Any]] = field(default_factory=list)
    market_health_parameters: List[Dict[str, Any]] = field(default_factory=list)
    market_deploy_tiers: List[Dict[str, Any]] = field(default_factory=list)
    exit_strategies: Dict[str, Any] = field(default_factory=dict)
    default_watchlist: Dict[str, Any] = field(default_factory=dict)
    strategies: List[Dict[str, Any]] = field(default_factory=list)
    symbol_allocations: Dict[str, float] = field(default_factory=dict)
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        config_path = os.path.join(_MODULE_DIR, "default.yaml")
        raw = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                raw = yaml.safe_load(f) or {}
        self._raw = raw
        self._load(raw)
        # Fix DB path AFTER _load so it isn't overwritten by YAML
        # On Streamlit Cloud /mount/src is read-only; use /tmp for SQLite
        if not os.path.isabs(self.database.path):
            data_dir = "/tmp/sqe_data"
            os.makedirs(data_dir, exist_ok=True)
            self.database.path = os.path.join(data_dir, "sqe.db")

    def _load(self, raw: Dict[str, Any]) -> None:
        if "app" in raw:
            self.app = AppConfig(**raw["app"])
        if "market" in raw:
            self.market = MarketConfig(**raw["market"])
        if "data" in raw:
            self.data = DataConfig(**raw["data"])
        if "database" in raw:
            self.database = DatabaseConfig(**raw["database"])
        if "logging" in raw:
            self.logging = LoggingConfig(**raw["logging"])
        if "etf_capital" in raw:
            ec = raw["etf_capital"]
            self.etf_capital = CapitalConfig(
                total=ec.get("total", 2000000),
                num_chunks=ec.get("num_chunks", 5),
                chunk_percentages=ec.get("chunk_percentages", [20, 20, 20, 20, 20]),
                next_buy_triggers=ec.get("next_buy_triggers", [1.0, 1.0, 1.0, 2.0, 3.0]),
            )
        if "stock_capital" in raw:
            sc = raw["stock_capital"]
            chunk_pcts = sc.get("chunk_percentages", [35, 35, 30])
            self.stock_capital = CapitalConfig(
                total=sc.get("total", 1000000),
                max_per_stock=sc.get("max_per_stock", 100000),
                num_stocks=sc.get("num_stocks", 10),
                num_chunks=sc.get("num_chunks", len(chunk_pcts)),
                chunk_percentages=chunk_pcts,
            )
        if "health_scores" in raw:
            hs = raw["health_scores"]
            self.health_scores = HealthScoreThresholds(**hs)
        if "profit_management" in raw:
            pm = raw["profit_management"]
            self.profit_management = ProfitManagementConfig(**pm)
        if "health_parameters" in raw:
            self.health_parameters = raw["health_parameters"]
        if "stock_health_parameters" in raw:
            self.stock_health_parameters = raw["stock_health_parameters"]
        if "market_health_parameters" in raw:
            self.market_health_parameters = raw["market_health_parameters"]
        if "market_deploy_tiers" in raw:
            self.market_deploy_tiers = raw["market_deploy_tiers"]
        if "exit_strategies" in raw:
            self.exit_strategies = raw["exit_strategies"]
        if "default_watchlist" in raw:
            self.default_watchlist = raw["default_watchlist"]
        if "strategies" in raw:
            self.strategies = raw["strategies"]

    def reload(self) -> None:
        """Reload settings from disk."""
        config_path = os.path.join(_MODULE_DIR, "default.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                raw = yaml.safe_load(f)
            self._raw = raw
            self._load(raw)
