"""Risk Parity — inverse-volatility weighted monthly allocation."""

from __future__ import annotations

import pandas as pd

from core.strategies.registry import register_strategy


@register_strategy(
    key="risk_parity", label="Risk Par.", category="portfolio",
    desc="低波动, 回撤控制最优",
    params={
        "lookback": {"type": "int", "default": 63, "min": 20, "max": 250, "desc": "波动率窗口(交易日)"},
        "top_n": {"type": "int", "default": 30, "min": 5, "max": 100, "desc": "入选股票数"},
        "min_weight": {"type": "float", "default": 0.005, "min": 0.001, "max": 0.05, "desc": "最小权重"},
    },
)
def signals_risk_parity(pivot: pd.DataFrame, params: dict | None = None) -> dict:
    p = params or {}
    lookback = int(p.get("lookback", 63))
    top_n = int(p.get("top_n", 30))
    min_w = float(p.get("min_weight", 0.005))
    sim_start = p.get("_sim_start")  # injected by orchestrator

    ss: dict[str, list] = {}
    rets = pivot.pct_change(fill_method=None).iloc[1:]
    dates = sorted(rets.index)
    if sim_start:
        bt_dates = [d for d in dates if d >= pd.Timestamp(sim_start)]
    else:
        bt_dates = dates[lookback:] if len(dates) > lookback else []
    if not bt_dates:
        return ss
    rb_dates = pd.date_range(bt_dates[0], dates[-1], freq="ME")
    for rd in rb_dates:
        nearest_idx = rets.index.get_indexer([rd], method="nearest")[0]
        if nearest_idx < lookback or nearest_idx >= len(dates):
            continue
        past = rets.iloc[max(0, nearest_idx - lookback):nearest_idx].ffill()
        if past.shape[0] < 20:
            continue
        vols = past.std()
        vols = vols[vols > 0]
        if vols.empty:
            continue
        inv_vol = 1.0 / vols
        w = inv_vol / inv_vol.sum()
        top_codes = w.nlargest(top_n)
        nearest_dt = rets.index[nearest_idx]
        month_end = nearest_dt + pd.DateOffset(months=1)
        month_dates = [d for d in dates if nearest_dt <= d <= month_end]
        for d in month_dates:
            dt = str(d.date())
            for code, weight in top_codes.items():
                if weight > min_w:
                    ss.setdefault(dt, []).append({"code": code, "action": "buy", "weight": weight})
    return ss
