"""
Backtest service — arbitrary-range backtests reusing signal_service + sim_engine.

Same execution semantics as the daily simulation (T-1 signal → T execution,
full costs, per-strategy rebalance_days). Used by:
  - /lab web backtest panel (background job)
  - scripts/gbr_validation.py (AM GBR validation report)
"""

from __future__ import annotations

import json
import logging

import pandas as pd

from core.strategies.registry import get_spec, scan_strategies
from kernel.sim_engine import (CostModel, DEFAULT_COSTS, INITIAL_CASH,
                                simulate_strategy, summary_metrics)
from services.data_service import load_pool
from services.market_service import benchmark_window
from services.signal_service import generate_all_signals

logger = logging.getLogger(__name__)


def run_backtest(strategies: list[str], start: str, end: str | None = None,
                 pool: str = "csi500", rb_overrides: dict[str, int] | None = None,
                 update_data: bool = False, costs: CostModel | None = None,
                 persist: bool = True, tag: str = "", note: str = "") -> dict:
    """Backtest strategies over [start, end]. Returns metrics + equity curves per mode.

    With ``persist=True`` (default) each strategy/mode combination is also written
    to research.db as a run, so results survive a restart and can be compared
    later from /research/runs. Set persist=False for throwaway runs.
    """
    import time

    from research.metrics import full_metrics
    from research.store import data_version, save_run

    scan_strategies()
    from services.data_service import auto_update
    t0 = time.time()
    df, _, _ = auto_update(pool) if update_data else (load_pool(pool), "", 0)
    if df.empty:
        raise RuntimeError(f"No data for pool {pool}")
    pivot = df.pivot(index="date", columns="code", values="close")

    sim_dates = [d for d in pivot.index if d >= pd.Timestamp(start)]
    if end:
        sim_dates = [d for d in sim_dates if d <= pd.Timestamp(end)]
    if not sim_dates:
        raise RuntimeError(f"No trading days in range {start} ~ {end}")

    all_sigs = generate_all_signals(pivot, start, strategies, df=df)

    bench = benchmark_window(start, end or str(sim_dates[-1].date()))
    bench_start_val = float(bench.iloc[0]) if len(bench) else None

    cm = costs or DEFAULT_COSTS
    dver = data_version(df)
    w_start, w_end = str(sim_dates[0].date()), str(sim_dates[-1].date())

    results = {}
    for sn in strategies:
        spec = get_spec(sn)
        if spec is None:
            continue
        rb = (rb_overrides or {}).get(sn, spec.rebalance_days)
        res = simulate_strategy(pivot, all_sigs.get(sn, {}), sn, sim_dates,
                                bench_start=bench_start_val, benchmark=bench,
                                rebalance_days=rb, max_positions=spec.max_positions,
                                costs=cm)
        entry = {"label": spec.label, "rebalance_days": rb}
        for mode, r in res.items():
            m = summary_metrics(r["snapshots"])
            entry[mode] = {**m, "costs": r["costs"], "final_equity": r["final_equity"],
                           "dates": [s["date"] for s in r["snapshots"]],
                           "equity": [s["equity"] for s in r["snapshots"]],
                           "n_trades": len(r["trades"]),
                           "turnover": round(sum(t["value"] for t in r["trades"]), 2)}
            if persist:
                try:
                    import hashlib
                    from core.strategies.registry import get_params
                    effective_params = {**get_params(sn), "rebalance_days": rb, "max_positions": spec.max_positions}
                    params_hash = hashlib.md5(
                        json.dumps(effective_params, sort_keys=True).encode()
                    ).hexdigest()[:8]
                    rid = save_run(
                        strategy=sn, label=spec.label, mode=mode,
                        params=effective_params, params_hash=params_hash,
                        window_start=w_start, window_end=w_end, n_days=len(sim_dates),
                        pool=pool, rebalance_days=rb, max_positions=spec.max_positions,
                        cost=cm.to_dict(), data_ver=dver, kind="backtest",
                        tag=tag, note=note,
                        metrics=full_metrics(r["snapshots"], r["trades"], INITIAL_CASH),
                        equity=r["snapshots"], trades=r["trades"],
                        duration_sec=time.time() - t0)
                    entry[mode]["run_id"] = rid
                except Exception as e:                       # never fail a backtest on a store error
                    logger.warning("Persist run failed for %s/%s: %s", sn, mode, e)
        results[sn] = entry

    return {"start": w_start, "end": w_end,
            "n_days": len(sim_dates), "pool": pool,
            "bench_ret": round((bench.iloc[-1] / bench_start_val - 1) * 100, 2) if bench_start_val else 0,
            "results": results}
