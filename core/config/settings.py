"""
Configuration — single source of truth for all tunable parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "cache"


@dataclass(frozen=True)
class Universe:
    """Stock pool definitions."""

    csi800: list[str] = field(default_factory=lambda: ["000906"])  # 中证800
    csi500: list[str] = field(default_factory=lambda: ["000905"])  # 中证500

    @property
    def all_pools(self) -> dict[str, list[str]]:
        return {"csi800": self.csi800, "csi500": self.csi500}


@dataclass(frozen=True)
class Period:
    train_start: str = "2019-01-01"
    train_end: str = "2023-12-31"
    backtest_start: str = "2024-01-01"
    backtest_end: str = "2026-06-30"


@dataclass(frozen=True)
class CostConfig:
    commission: float = 0.001  # 0.1% per side
    slippage: float = 0.001  # 0.1% slippage
    stamp_duty: float = 0.001  # 0.1% sell only (A-share)


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 1_000_000.0
    position_limit: int = 20  # max concurrent positions
    max_position_pct: float = 0.05  # 5% per stock


@dataclass(frozen=True)
class Config:
    universe: Universe = field(default_factory=Universe)
    period: Period = field(default_factory=Period)
    cost: CostConfig = field(default_factory=CostConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    frequency: str = "daily"  # daily | weekly | monthly
    freq_map: dict[str, str] = field(default_factory=lambda: {"daily": "1d", "weekly": "1w", "monthly": "1M"})


config = Config()
