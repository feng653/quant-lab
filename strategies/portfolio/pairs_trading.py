"""
Pairs Trading strategy — cointegration-based statistical arbitrage.

Source: je-suis-tm/quant-trading ★ 10.4k
Logic: Find cointegrated pairs → trade spread deviation from mean at 2σ.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP


class PairsTradingStrategy(BaseStrategy):
    meta = STRATEGY_MAP["pairs_trading"]

    def __init__(self, pool_name: str = "csi800", lookback: int = 120, entry_z: float = 2.0, exit_z: float = 0.5, max_pairs: int = 20) -> None:
        super().__init__(pool_name)
        self.lookback = lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.max_pairs = max_pairs
        self.pairs: list[tuple[str, str]] = []
        self.meta.params = {"lookback": lookback, "entry_z": entry_z, "exit_z": exit_z, "max_pairs": max_pairs}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        self.price_pivot = self.df.pivot(index="date", columns="code", values="close")

    def _find_cointegrated_pairs(self) -> list[tuple[str, str]]:
        """Find cointegrated pairs from the stock universe using Engle-Granger test."""
        codes = list(self.price_pivot.columns)
        pairs_with_pvalue: list[tuple[tuple[str, str], float]] = []

        for a, b in combinations(codes, 2):
            price_a = self.price_pivot[a].dropna()
            price_b = self.price_pivot[b].dropna()
            common_idx = price_a.index.intersection(price_b.index)
            if len(common_idx) < self.lookback:
                continue
            p_a = price_a.loc[common_idx[-self.lookback :]]
            p_b = price_b.loc[common_idx[-self.lookback :]]
            _, pvalue, _ = coint(p_a, p_b)
            if pvalue < 0.05:
                pairs_with_pvalue.append(((a, b), pvalue))

        pairs_with_pvalue.sort(key=lambda x: x[1])
        return [p[0] for p in pairs_with_pvalue[: self.max_pairs]]

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        self.pairs = self._find_cointegrated_pairs()
        signals: dict[str, list[dict[str, Any]]] = {}

        for a, b in self.pairs:
            pa = self.price_pivot[a].dropna()
            pb = self.price_pivot[b].dropna()
            common = pa.index.intersection(pb.index)

            spread = pa[common] - pb[common]
            spread_mean = spread.rolling(self.lookback, min_periods=self.lookback).mean()
            spread_std = spread.rolling(self.lookback, min_periods=self.lookback).std()
            zscore = (spread - spread_mean) / spread_std.replace(0, np.nan)

            for i in range(self.lookback, len(zscore) - 1):
                z = zscore.iloc[i]
                z_prev = zscore.iloc[i - 1] if i > 0 else z
                dt = str(zscore.index[i].date())

                if abs(z) > self.entry_z and abs(z_prev) <= self.entry_z:
                    long_target = b if z > 0 else a
                    short_target = a if z > 0 else b
                    signals.setdefault(dt, []).append({"code": long_target, "action": "buy", "weight": 0.5})
                    signals.setdefault(dt, []).append({"code": short_target, "action": "sell", "weight": 0.5})
                elif abs(z) < self.exit_z:
                    signals.setdefault(dt, []).append({"code": a, "action": "sell"})
                    signals.setdefault(dt, []).append({"code": b, "action": "sell"})

        return signals
