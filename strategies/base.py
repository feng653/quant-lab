"""
Strategy base class — common interface for all strategies.

Every strategy must implement:
  - init(): prepare indicators
  - next(i): process bar i, optionally submit orders
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StrategyMeta:
    """Metadata record for each strategy — provenance tracking."""

    name: str
    source_project: str  # GitHub org/repo
    source_stars: int
    category: str  # technical | factor | ml | portfolio
    description: str
    paper_ref: str = ""
    params: dict[str, Any] = field(default_factory=dict)


class BaseStrategy(ABC):
    """Abstract strategy interface.

    Subclasses live in strategies/{category}/ and each one
    exports a STRATEGY_META instance declaring its provenance.
    """

    meta: StrategyMeta

    def __init__(self, pool_name: str = "csi800") -> None:
        self.pool = pool_name
        self.signals: dict[str, list[dict[str, Any]]] = {}  # date -> [{code, action, weight}]

    @abstractmethod
    def prepare_data(self, df: "pd.DataFrame") -> None: ...

    @abstractmethod
    def generate_signals(self) -> dict[str, list[dict[str, Any]]]: ...

    def name(self) -> str:
        return self.meta.name
