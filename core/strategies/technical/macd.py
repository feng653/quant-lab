"""MACD Signal — DIF/DEA golden cross momentum entry."""

from __future__ import annotations

import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="macd_signal", label="MACD", category="technical",
    desc="趋势+动量, 三重确认",
    params={
        "fast": {"type": "int", "default": 12, "min": 3, "max": 50, "desc": "DIF 快线 EMA"},
        "slow": {"type": "int", "default": 26, "min": 10, "max": 100, "desc": "DIF 慢线 EMA"},
        "signal": {"type": "int", "default": 9, "min": 2, "max": 30, "desc": "DEA 信号线"},
    },
)
def signals_macd(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    p = params or {}
    fast, slow, sig = int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal", 9))
    ss: dict[str, list] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < slow + sig + 15:
            continue
        ema_f = s.ewm(span=fast, adjust=False).mean()
        ema_s = s.ewm(span=slow, adjust=False).mean()
        dif = ema_f - ema_s
        dea = dif.ewm(span=sig, adjust=False).mean()
        golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        for d_ in golden[golden].index:
            ss.setdefault(str(d_.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss
