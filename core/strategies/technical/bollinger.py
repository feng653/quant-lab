"""
Bollinger Bands Breakout strategy.

Source: je-suis-tm/quant-trading ★ 10.4k
Logic: Price breaks above upper band → buy; reverts to middle → sell.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP


class BollingerStrategy(BaseStrategy):
    meta = STRATEGY_MAP["bollinger_breakout"]

    def __init__(self, pool_name: str = "csi800", window: int = 20, num_std: float = 2.0) -> None:
        super().__init__(pool_name)
        self.window = window
        self.num_std = num_std
        self.meta.params = {"window": window, "num_std": num_std}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        grouped = self.df.groupby("code")["close"]
        self.df["ma"] = grouped.transform(lambda x: x.rolling(self.window, min_periods=self.window).mean())
        self.df["std"] = grouped.transform(lambda x: x.rolling(self.window, min_periods=self.window).std())
        self.df["upper"] = self.df["ma"] + self.num_std * self.df["std"]
        self.df["lower"] = self.df["ma"] - self.num_std * self.df["std"]
        self.df["above_upper"] = (self.df["close"] > self.df["upper"]).astype(int)
        self.df["prev_above"] = self.df.groupby("code")["above_upper"].shift(1).fillna(0)

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        signals: dict[str, list[dict[str, Any]]] = {}
        # Breakout above upper band
        buy = (self.df["prev_above"] == 0) & (self.df["above_upper"] == 1)
        # Revert below middle
        sell = (self.df["close"] < self.df["ma"]) & (self.df["close"].shift(1) >= self.df["ma"].shift(1))

        for _, row in self.df[buy].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "buy", "weight": 1.0})

        for _, row in self.df[sell].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "sell"})

        return signals
