"""
MACD Signal strategy.

Source: je-suis-tm/quant-trading ★ 10.4k
Logic: DIF crosses above DEA → golden cross (buy); DIF below DEA → death cross (sell).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP


class MACDStrategy(BaseStrategy):
    meta = STRATEGY_MAP["macd_signal"]

    def __init__(self, pool_name: str = "csi800", fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        super().__init__(pool_name)
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.meta.params = {"fast": fast, "slow": slow, "signal": signal}

    def _ema(self, series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        grouped = self.df.groupby("code")["close"]
        ema_fast = grouped.transform(lambda x: self._ema(x, self.fast))
        ema_slow = grouped.transform(lambda x: self._ema(x, self.slow))
        self.df["dif"] = ema_fast - ema_slow
        self.df["dea"] = self.df.groupby("code")["dif"].transform(
            lambda x: self._ema(x, self.signal_period)
        )
        self.df["macd_bar"] = 2 * (self.df["dif"] - self.df["dea"])
        self.df["golden"] = (
            (self.df["dif"] > self.df["dea"]) & (self.df["dif"].shift(1) <= self.df["dea"].shift(1))
        )
        self.df["death"] = (
            (self.df["dif"] < self.df["dea"]) & (self.df["dif"].shift(1) >= self.df["dea"].shift(1))
        )

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        signals: dict[str, list[dict[str, Any]]] = {}
        for _, row in self.df[self.df["golden"]].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "buy", "weight": 1.0})
        for _, row in self.df[self.df["death"]].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "sell"})
        return signals
