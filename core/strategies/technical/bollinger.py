"""Bollinger Breakout — volatility breakout above upper band, exit at mid band."""

from __future__ import annotations

import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="bollinger_breakout", label="Bollinger", category="technical",
    desc="波动率突破, 换手极高",
    params={
        "window": {"type": "int", "default": 20, "min": 5, "max": 60, "desc": "布林带窗口"},
        "num_std": {"type": "float", "default": 2.0, "min": 1.0, "max": 3.5, "desc": "标准差倍数"},
    },
)
def signals_bollinger(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    p = params or {}
    window, nstd = int(p.get("window", 20)), float(p.get("num_std", 2.0))
    ss: dict[str, list] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < window + 10:
            continue
        ma = s.rolling(window).mean()
        std = s.rolling(window).std()
        upper = ma + nstd * std
        buy = (s.shift(1) < upper.shift(1)) & (s > upper)
        sell = (s < ma) & (s.shift(1) >= ma.shift(1))
        for d_ in buy[buy].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
        for d_ in sell[sell].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "sell"})
    return ss
