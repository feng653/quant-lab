"""RSI Reversal — oversold mean-reversion entry."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="rsi_reversal", label="RSI Rev.", category="technical",
    desc="均值回归, 牛市逆势",
    params={
        "period": {"type": "int", "default": 14, "min": 5, "max": 50, "desc": "RSI 周期"},
        "oversold": {"type": "float", "default": 30.0, "min": 10.0, "max": 45.0, "desc": "超卖阈值"},
    },
)
def signals_rsi(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    p = params or {}
    period, oversold = int(p.get("period", 14)), float(p.get("oversold", 30.0))
    ss: dict[str, list] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < period * 2 + 2:
            continue
        d = s.diff()
        g = d.clip(lower=0).ewm(span=period, adjust=False).mean()
        l = (-d).clip(lower=0).ewm(span=period, adjust=False).mean()
        rs = g / l.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        buy = (rsi.shift(1) <= oversold) & (rsi > oversold)
        for d_ in buy[buy].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss
