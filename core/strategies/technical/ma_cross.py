"""MA Cross — dual moving-average golden-cross trend following."""

from __future__ import annotations

import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="ma_cross", label="MA Cross", category="technical",
    desc="趋势跟踪, 信号稀少质量高",
    params={
        "fast": {"type": "int", "default": 20, "min": 2, "max": 120, "desc": "快线均线窗口"},
        "slow": {"type": "int", "default": 60, "min": 5, "max": 250, "desc": "慢线均线窗口"},
    },
)
def signals_ma_cross(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    p = params or {}
    fast, slow = int(p.get("fast", 20)), int(p.get("slow", 60))
    ss: dict[str, list] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < slow + 20:
            continue
        mf = s.rolling(fast).mean()
        ms = s.rolling(slow).mean()
        cross = (mf > ms) & (mf.shift(1) <= ms.shift(1))
        for d in cross[cross].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss
