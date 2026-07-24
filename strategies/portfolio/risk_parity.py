"""
Risk Parity portfolio strategy.

Source: robertmartin8/PyPortfolioOpt ★ 4.8k
Logic: Monthly rebalance to equal-risk-contribution weights.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy, StrategyMeta
from strategies.stars_tags import STRATEGY_MAP

logger = logging.getLogger(__name__)


class RiskParityStrategy(BaseStrategy):
    meta = STRATEGY_MAP["risk_parity"]

    def __init__(self, pool_name: str = "csi800", lookback: int = 60, top_n: int = 50, rebalance_freq: str = "ME") -> None:
        super().__init__(pool_name)
        self.lookback = lookback
        self.top_n = top_n
        self.rebalance_freq = rebalance_freq
        self.meta.params = {"lookback": lookback, "top_n": top_n, "rebalance_freq": rebalance_freq}

    def prepare_data(self, df: pd.DataFrame) -> None:
        self.df = df.sort_values(["code", "date"]).copy()
        self.df["ret"] = self.df.groupby("code")["close"].pct_change()
        self.ret_pivot = self.df.pivot(index="date", columns="code", values="ret")

    def _select_top_by_volume(self, date_str: str) -> list[str]:
        """Select top N stocks by recent average daily volume."""
        dt = pd.Timestamp(date_str)
        recent = self.df[(self.df["date"] >= dt - pd.DateOffset(days=self.lookback)) & (self.df["date"] <= dt)]
        vol_mean = recent.groupby("code")["volume"].mean().sort_values(ascending=False)
        return vol_mean.head(self.top_n).index.tolist()

    def _risk_parity_weights(self, returns: pd.DataFrame) -> dict[str, float]:
        """Compute risk parity weights (inverse-volatility heuristic)."""
        vols = returns.std()
        inv_vol = 1.0 / vols.replace(0, np.nan)
        inv_vol = inv_vol.dropna()
        if inv_vol.empty:
            return {}
        weights = inv_vol / inv_vol.sum()
        return weights.to_dict()

    def generate_signals(self) -> dict[str, list[dict[str, Any]]]:
        signals: dict[str, list[dict[str, Any]]] = {}

        all_dates = sorted(self.ret_pivot.index)
        rebalance_dates = pd.date_range(
            start=all_dates[0], end=all_dates[-1], freq=self.rebalance_freq
        )

        for rd in rebalance_dates:
            if rd not in self.ret_pivot.index:
                nearest = min(all_dates, key=lambda d: abs((d - rd).days))
                if abs((nearest - rd).days) > 5:
                    continue
                rd = nearest

            rd_idx = self.ret_pivot.index.get_loc(rd)
            start_idx = max(0, rd_idx - self.lookback)
            lookback_rets = self.ret_pivot.iloc[start_idx:rd_idx]

            top_codes = self._select_top_by_volume(str(rd.date()))
            lookback_rets = lookback_rets[top_codes].dropna(axis=1, how="all")

            weights = self._risk_parity_weights(lookback_rets)
            d = str(rd.date())
            for code, w in weights.items():
                if w > 0.001:
                    signals.setdefault(d, []).append({"code": code, "action": "buy", "weight": w})

        return signals
