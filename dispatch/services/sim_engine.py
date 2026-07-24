"""
Daily simulation engine — deterministic full-window re-simulation.

Each run re-simulates from simulation_start using the updated price pivot and
pre-computed signals, then refreshes SQLite. No incremental state patching:
idempotent, drift-free, safe to re-run any time.

Two position-sizing modes are simulated in parallel for every strategy:
  equal    — split cash equally across buy candidates (baseline)
  adaptive — exposure scaled by market volatility:
             exposure = clamp(TARGET_VOL / market_vol_20d, 0.3, 1.0)
             high volatility → smaller invested fraction, rest stays in cash.

Execution semantics (identical to research backtest):
  - sell signals executed on the day AFTER the signal (T+1 at close)
  - every RB-th trading day is a rebalance day: liquidate everything, then
    buy per the previous day's signals
  - costs: commission 0.1% (both sides), stamp duty 0.1% (sell), slippage 0.1%
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

INITIAL_CASH = 1_000_000.0
COMMISSION = 0.001
SLIPPAGE = 0.001
STAMP_DUTY = 0.001
MAX_POS = 20
RB = 30
TARGET_VOL = 0.15
MIN_EXPOSURE, MAX_EXPOSURE = 0.3, 1.0

MODES = ("equal", "adaptive")


def _market_vol_series(pivot: pd.DataFrame) -> pd.Series:
    """Annualized 20d volatility of the equal-weight pool return."""
    rets = pivot.pct_change(fill_method=None)
    pool_ret = rets.mean(axis=1)
    return pool_ret.rolling(20).std() * np.sqrt(252)


def simulate_strategy(pivot: pd.DataFrame, signals: dict, strategy: str,
                      sim_dates: list[pd.Timestamp], bench_start: float | None = None,
                      benchmark: pd.Series | None = None) -> dict:
    """Run both modes for one strategy over sim_dates.

    Returns {mode: {"snapshots": [...], "trades": [...], "costs": {...},
                    "final": {...}, "positions": {...}}}
    """
    all_dates = list(pivot.index)
    date_pos = {d: i for i, d in enumerate(all_dates)}
    mvol = _market_vol_series(pivot)

    results = {}
    for mode in MODES:
        cash = INITIAL_CASH
        pos: dict[str, float] = {}
        last_px: dict[str, float] = {}
        snaps, trades = [], []
        cost_comm = cost_stamp = cost_slip = 0.0
        prev_eq = None

        for dt in sim_dates:
            prices = pivot.loc[dt].dropna()
            for c, p in prices.items():
                last_px[c] = float(p)
            di = date_pos[dt]
            is_rb = di % RB == 0
            prev_dt = all_dates[di - 1] if di > 0 else dt
            day_sigs = signals.get(str(prev_dt.date()), [])
            buys = [s for s in day_sigs if s["action"] == "buy"]
            sells = [s for s in day_sigs if s["action"] == "sell"]
            d_str = str(dt.date())

            # 1) sells
            for s in sells:
                c = s["code"]
                if c in pos and c in prices.index:
                    px = float(prices[c]) * (1 - SLIPPAGE)
                    val = pos[c] * px
                    comm = val * COMMISSION
                    stamp = val * STAMP_DUTY
                    slip = pos[c] * float(prices[c]) * SLIPPAGE
                    cash += val - comm - stamp
                    cost_comm += comm; cost_stamp += stamp; cost_slip += slip
                    trades.append({"date": d_str, "strategy": strategy, "mode": mode, "code": c,
                                   "action": "sell", "shares": int(pos[c]), "price": round(px, 3),
                                   "value": round(val, 2), "commission": round(comm, 2),
                                   "stamp_duty": round(stamp, 2), "slippage_cost": round(slip, 2)})
                    del pos[c]

            # 2) rebalance liquidation
            if is_rb:
                for c in list(pos):
                    px_raw = last_px.get(c)
                    if px_raw is None:
                        continue
                    px = px_raw * (1 - SLIPPAGE)
                    val = pos[c] * px
                    comm = val * COMMISSION
                    stamp = val * STAMP_DUTY
                    slip = pos[c] * px_raw * SLIPPAGE
                    cash += val - comm - stamp
                    cost_comm += comm; cost_stamp += stamp; cost_slip += slip
                    trades.append({"date": d_str, "strategy": strategy, "mode": mode, "code": c,
                                   "action": "sell", "shares": int(pos[c]), "price": round(px, 3),
                                   "value": round(val, 2), "commission": round(comm, 2),
                                   "stamp_duty": round(stamp, 2), "slippage_cost": round(slip, 2)})
                    del pos[c]

            # 3) buys on rebalance day
            if is_rb and buys:
                valid = [s for s in buys if s["code"] in prices.index and s["code"] not in pos]
                if valid:
                    if mode == "adaptive":
                        v = mvol.get(dt, np.nan)
                        exposure = float(np.clip(TARGET_VOL / v, MIN_EXPOSURE, MAX_EXPOSURE)) if pd.notna(v) and v > 0 else 1.0
                    else:
                        exposure = 1.0
                    valid = valid[:MAX_POS]
                    w = exposure / len(valid)
                    for s in valid:
                        c = s["code"]
                        bp = float(prices[c]) * (1 + SLIPPAGE)
                        sh = int(cash * w // bp // 100) * 100
                        if sh >= 100:
                            cost = sh * bp
                            comm = cost * COMMISSION
                            if cost + comm <= cash:
                                slip = sh * float(prices[c]) * SLIPPAGE
                                cash -= cost + comm
                                cost_comm += comm; cost_slip += slip
                                pos[c] = sh
                                trades.append({"date": d_str, "strategy": strategy, "mode": mode, "code": c,
                                               "action": "buy", "shares": int(sh), "price": round(bp, 3),
                                               "value": round(cost, 2), "commission": round(comm, 2),
                                               "stamp_duty": 0.0, "slippage_cost": round(slip, 2)})

            # 4) mark to market
            eq = cash + sum(sh * last_px.get(c, 0.0) for c, sh in pos.items())
            bench_ret = 0.0
            if benchmark is not None and bench_start and dt in benchmark.index:
                bench_ret = float(benchmark[dt] / bench_start - 1)
            snaps.append({"date": d_str, "strategy": strategy, "mode": mode,
                          "equity": round(eq, 2), "cash": round(cash, 2),
                          "n_positions": len(pos),
                          "daily_ret": round(eq / prev_eq - 1, 6) if prev_eq else 0.0,
                          "cum_ret": round(eq / INITIAL_CASH - 1, 6),
                          "bench_ret": round(bench_ret, 6)})
            prev_eq = eq

        results[mode] = {
            "snapshots": snaps, "trades": trades,
            "costs": {"commission": round(cost_comm, 2), "stamp_duty": round(cost_stamp, 2),
                      "slippage": round(cost_slip, 2),
                      "total": round(cost_comm + cost_stamp + cost_slip, 2)},
            "final_equity": snaps[-1]["equity"] if snaps else INITIAL_CASH,
            "positions": dict(pos),
            "cash": round(cash, 2),
        }
    return results


def summary_metrics(snaps: list[dict]) -> dict:
    """Summary stats from a snapshot list (single mode)."""
    if len(snaps) < 2:
        return {"total_return": 0, "annual_return": 0, "sharpe": 0, "max_dd": 0,
                "today_return": 0, "volatility": 0, "win_rate": 0}
    eq = pd.Series([s["equity"] for s in snaps])
    rets = pd.Series([s["daily_ret"] for s in snaps[1:]])
    total = eq.iloc[-1] / INITIAL_CASH - 1
    years = max(len(eq) / 252, 1 / 252)
    annual = (1 + total) ** (1 / years) - 1
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else 0.0
    sharpe = float((annual - 0.02) / vol) if vol > 0 else 0.0
    peak = eq.cummax()
    max_dd = float(((eq - peak) / peak).min())
    return {"total_return": round(total * 100, 2), "annual_return": round(annual * 100, 2),
            "sharpe": round(sharpe, 3), "max_dd": round(max_dd * 100, 2),
            "today_return": round(rets.iloc[-1] * 100, 2) if len(rets) else 0.0,
            "volatility": round(vol * 100, 2),
            "win_rate": round(float((rets > 0).mean()) * 100, 1) if len(rets) else 0.0}
