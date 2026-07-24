"""
Dual Moving Average Crossover strategy.

Source: je-suis-tm/quant-trading ★ 10.4k
Logic: Buy when short MA crosses above long MA, sell on opposite cross.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP


class MACrossStrategy(BaseStrategy):
    meta = STRATEGY_MAP["ma_cross"]

    def __init__(self, pool_name: str = "csi800", short: int = 20, long: int = 60) -> None:
        super().__init__(pool_name)
        self.short = short
        self.long = long
        self.meta.params = {"short_window": short, "long_window": long}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        self.df["ma_short"] = self.df.groupby("code")["close"].transform(
            lambda x: x.rolling(self.short, min_periods=self.short).mean()
        )
        self.df["ma_long"] = self.df.groupby("code")["close"].transform(
            lambda x: x.rolling(self.long, min_periods=self.long).mean()
        )
        self.df["signal"] = (self.df["ma_short"] > self.df["ma_long"]).astype(int)
        # crossover = signal went from 0 to 1
        self.df["cross"] = self.df.groupby("code")["signal"].diff().fillna(0)

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        buy_signals = self.df[self.df["cross"] == 1]
        sell_signals = self.df[self.df["cross"] == -1]

        signals: dict[str, list[dict[str, Any]]] = {}
        for _, row in buy_signals.iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "buy", "weight": 1.0})

        for _, row in sell_signals.iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "sell"})

        return signals
