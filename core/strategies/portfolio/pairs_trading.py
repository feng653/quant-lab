"""Pairs Trading — cointegration z-score mean reversion.

NOTE: disabled by default. A-shares cannot be shorted, so the short leg of
each pair cannot be executed — the strategy degrades to directional long
bets and performed poorly (-55.78% in the 2026-05~07 simulation window).
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="pairs_trading", label="Pairs Tr.", category="portfolio",
    desc="统计套利, 需做空能力 (A股无法做空, 已停用)",
    enabled_by_default=False,
    note="A股无法做空, 配对空头腿无法执行, 模拟亏损严重, 2026-07-25 停用",
    params={
        "lookback": {"type": "int", "default": 120, "min": 40, "max": 250, "desc": "协整/价差窗口"},
        "z_entry": {"type": "float", "default": 2.0, "min": 1.0, "max": 4.0, "desc": "开仓Z阈值"},
        "z_exit": {"type": "float", "default": 0.5, "min": 0.1, "max": 1.5, "desc": "平仓Z阈值"},
        "max_pairs": {"type": "int", "default": 30, "min": 5, "max": 100, "desc": "最大配对数"},
        "universe": {"type": "int", "default": 60, "min": 20, "max": 200, "desc": "配对扫描股票数"},
    },
)
def signals_pairs_trading(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    from statsmodels.tsa.stattools import coint

    p = params or {}
    lookback = int(p.get("lookback", 120))
    z_entry, z_exit = float(p.get("z_entry", 2.0)), float(p.get("z_exit", 0.5))
    max_pairs, universe = int(p.get("max_pairs", 30)), int(p.get("universe", 60))

    ss: dict[str, list] = {}
    codes = list(pivot.columns)
    pairs_found = 0
    for a, b in combinations(codes[:universe], 2):
        pa = pivot[a].dropna()
        pb = pivot[b].dropna()
        ci = pa.index.intersection(pb.index)
        if len(ci) < lookback:
            continue
        try:
            _, pv, _ = coint(pa[ci[-lookback:]], pb[ci[-lookback:]])
        except Exception:
            continue
        if pv >= 0.05:
            continue
        pairs_found += 1
        if pairs_found > max_pairs:
            break
        spread = pa[ci] - pb[ci]
        sm = spread.rolling(lookback).mean()
        ssd_ = spread.rolling(lookback).std()
        z = (spread - sm) / ssd_.replace(0, np.nan)
        prev_z = z.shift(1)
        for i_ in range(lookback, len(z)):
            if abs(z.iloc[i_]) > z_entry and abs(prev_z.iloc[i_]) <= z_entry:
                dt = str(z.index[i_].date())
                ss.setdefault(dt, []).append({"code": b if z.iloc[i_] > 0 else a, "action": "buy", "weight": 0.1})
                ss.setdefault(dt, []).append({"code": a if z.iloc[i_] > 0 else b, "action": "sell", "weight": 0.1})
            elif abs(z.iloc[i_]) < z_exit:
                dt = str(z.index[i_].date())
                ss.setdefault(dt, []).append({"code": a, "action": "sell"})
                ss.setdefault(dt, []).append({"code": b, "action": "sell"})
    return ss
