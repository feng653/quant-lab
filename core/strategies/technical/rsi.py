"""
RSI Mean-Reversion strategy.

Source: je-suis-tm/quant-trading ★ 10.4k
Logic: RSI < oversold threshold → buy; RSI > overbought threshold → sell.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP


class RSIStrategy(BaseStrategy):
    meta = STRATEGY_MAP["rsi_reversal"]

    def __init__(self, pool_name: str = "csi800", period: int = 14, oversold: int = 30, overbought: int = 70) -> None:
        super().__init__(pool_name)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.meta.params = {"period": period, "oversold": oversold, "overbought": overbought}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        delta = self.df.groupby("code")["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.groupby(self.df["code"]).transform(
            lambda x: x.rolling(self.period, min_periods=self.period).mean()
        )
        avg_loss = loss.groupby(self.df["code"]).transform(
            lambda x: x.rolling(self.period, min_periods=self.period).mean()
        )
        rs = avg_gain / avg_loss.replace(0, np.nan)
        self.df["rsi"] = 100 - (100 / (1 + rs))
        self.df["rsi_prev"] = self.df.groupby("code")["rsi"].shift(1)

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        signals: dict[str, list[dict[str, Any]]] = {}
        # Buy when RSI crosses above oversold
        buy_mask = (self.df["rsi_prev"] <= self.oversold) & (self.df["rsi"] > self.oversold)
        # Sell when RSI crosses below overbought
        sell_mask = (self.df["rsi_prev"] >= self.overbought) & (self.df["rsi"] < self.overbought)

        for _, row in self.df[buy_mask].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "buy", "weight": 1.0})

        for _, row in self.df[sell_mask].iterrows():
            d = str(row["date"].date())
            signals.setdefault(d, []).append({"code": row["code"], "action": "sell"})

        return signals
