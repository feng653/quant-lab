"""
Market environment service — classify the current regime from CSI 500 and
map regimes to suitable strategies. Also provides benchmark helpers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.data_service import load_benchmark

# Regime → suitable strategy keys
REGIME_STRATEGIES = {
    "bull":     ["ma_cross", "macd_signal", "alpha158_lgb_wf", "alpha158_xgb_wf"],
    "bear":     ["risk_parity", "bollinger_breakout", "pairs_trading"],
    "high_vol": ["risk_parity", "pairs_trading"],
    "choppy":   ["rsi_reversal", "pairs_trading", "bollinger_breakout"],
    "mild_up":  ["ma_cross", "macd_signal", "alpha158_lgb_wf"],
}

REGIME_DISPLAY = {
    "bull":     ("🐂 牛市", "趋势上行，顺势而为", "#c62828"),
    "bear":     ("🐻 熊市", "短期下跌，控制仓位", "#2e7d32"),
    "high_vol": ("🌊 高波动市", "波动放大，降低暴露", "#e65100"),
    "choppy":   ("📊 震荡市", "区间整理，均值回归", "#1565c0"),
    "mild_up":  ("📈 偏强震荡", "温和上行，均衡配置", "#6a1b9a"),
}


def classify_market() -> dict:
    """Classify current market regime from CSI 500 (needs ~60d history)."""
    bench = load_benchmark()  # full cached history
    if len(bench) < 63:
        return {"regime": "unknown", "label": "⚪ 数据不足", "desc": "", "color": "#666",
                "ret_20d": 0, "ret_60d": 0, "vol_20d": 0, "strategies": []}

    close = bench.iloc[-1]
    ret_20d = float(close / bench.iloc[-21] - 1) if len(bench) >= 21 else 0.0
    ret_60d = float(close / bench.iloc[-61] - 1) if len(bench) >= 61 else 0.0
    ma60 = float(bench.iloc[-60:].mean())
    vol_20d = float(bench.pct_change().iloc[-20:].std() * np.sqrt(252))

    if ret_60d > 0.10 and close > ma60:
        regime = "bull"
    elif ret_20d < -0.05:
        regime = "bear"
    elif vol_20d > 0.30:
        regime = "high_vol"
    elif abs(ret_20d) < 0.02:
        regime = "choppy"
    else:
        regime = "mild_up"

    label, desc, color = REGIME_DISPLAY[regime]
    return {"regime": regime, "label": label, "desc": desc, "color": color,
            "ret_20d": round(ret_20d * 100, 2), "ret_60d": round(ret_60d * 100, 2),
            "vol_20d": round(vol_20d * 100, 1),
            "bench_close": round(close, 1),
            "strategies": REGIME_STRATEGIES[regime]}


def benchmark_window(start: str, end: str | None = None) -> pd.Series:
    """Benchmark closes within the simulation window (for charts/metrics)."""
    s = load_benchmark(start=start)
    if end:
        s = s[s.index <= pd.Timestamp(end)]
    return s
