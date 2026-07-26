"""
Unified runner — single interface for backtest/production/sweep runs.

This is the kernel layer's canonical execution interface. Accepts a RunSpec,
executes the simulation via sim_engine, computes full metrics, and returns a
RunResult ready to be persisted to the experiment store or consumed by the
production pipeline.

Designed to be called from:
  - research web pages (user-initiated backtest)
  - parameter sweep engine (child runs)
  - production daily pipeline (dump to research.db for trend analysis)
  - scripts and notebooks

The old backtest_service.run_backtest() is now a thin wrapper over this.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from core.strategies.registry import get_spec, scan_strategies
from kernel.data_service import load_pool, auto_update
from kernel.sim_engine import (CostModel, DEFAULT_COSTS, INITIAL_CASH,
                                simulate_strategy, summary_metrics)
from research.metrics import full_metrics
from research.store import data_version
from services.market_service import benchmark_window

logger = logging.getLogger(__name__)


@dataclass
class RunSpec:
    """Immutable specification of a single run."""
    strategy: str
    start: str
    end: str | None = None
    pool: str = "csi500"
    mode: str = "equal"
    rebalance_days: int | None = None
    max_positions: int | None = None
    costs: CostModel = field(default_factory=lambda: DEFAULT_COSTS)
    update_data: bool = False
    kind: str = "backtest"
    parent_sweep_id: str | None = None
    tag: str = ""
    note: str = ""
    params: dict[str, Any] | None = None

    def __post_init__(self):
        scan_strategies()


@dataclass
class RunResult:
    """Complete output of a run — metrics, curves, trades, reproducibility."""
    run_id: str
    spec: RunSpec
    strategy_label: str
    window_start: str
    window_end: str
    n_days: int
    metrics: dict[str, float]
    snapshots: list[dict]
    trades: list[dict]
    costs_detail: dict
    data_ver: str
    duration_sec: float
    status: str = "done"
    error: str | None = None


def execute(spec: RunSpec, run_id: str | None = None) -> RunResult:
    """Execute a single run per the spec. Returns a complete RunResult."""
    from research.store import new_run_id

    rid = run_id or new_run_id()
    t0 = time.time()

    try:
        # 1) data
        df, _, _ = auto_update(spec.pool) if spec.update_data else (load_pool(spec.pool), "", 0)
        if df.empty:
            raise RuntimeError(f"No data for pool {spec.pool}")
        pivot = df.pivot(index="date", columns="code", values="close")

        sim_dates = [d for d in pivot.index if d >= pd.Timestamp(spec.start)]
        if spec.end:
            sim_dates = [d for d in sim_dates if d <= pd.Timestamp(spec.end)]
        if not sim_dates:
            raise RuntimeError(f"No trading days in range {spec.start} ~ {spec.end}")

        window_start = str(sim_dates[0].date())
        window_end = str(sim_dates[-1].date())

        # 2) signals
        from kernel.signal_service import generate_all_signals

        params_overrides = {spec.strategy: spec.params} if spec.params else None
        all_sigs = generate_all_signals(pivot, spec.start, [spec.strategy], df=df,
                                        params_overrides=params_overrides,
                                        cache_scope="research")
        sig_dict = all_sigs.get(spec.strategy, {})

        # 3) benchmark
        bench = benchmark_window(window_start, window_end)
        bench_start_val = float(bench.iloc[0]) if len(bench) else None

        # 4) simulate
        strategy_spec = get_spec(spec.strategy)
        if strategy_spec is None:
            raise RuntimeError(f"Strategy {spec.strategy} not registered")

        rb = spec.rebalance_days if spec.rebalance_days is not None else strategy_spec.rebalance_days
        mp = spec.max_positions if spec.max_positions is not None else strategy_spec.max_positions

        res = simulate_strategy(pivot, sig_dict, spec.strategy, sim_dates,
                                bench_start=bench_start_val, benchmark=bench,
                                rebalance_days=rb, max_positions=mp,
                                costs=spec.costs, modes=(spec.mode,),
                                initial_cash=INITIAL_CASH)

        mode_res = res[spec.mode]
        snaps = mode_res["snapshots"]
        trades = mode_res["trades"]

        # 5) metrics
        metrics = full_metrics(snaps, trades, initial=INITIAL_CASH)

        return RunResult(
            run_id=rid, spec=spec, strategy_label=strategy_spec.label,
            window_start=window_start, window_end=window_end, n_days=len(sim_dates),
            metrics=metrics, snapshots=snaps, trades=trades,
            costs_detail=mode_res["costs"], data_ver=data_version(df),
            duration_sec=time.time() - t0, status="done"
        )

    except Exception as e:
        logger.exception("Run %s failed: %s", rid, e)
        return RunResult(
            run_id=rid, spec=spec, strategy_label="", window_start="", window_end="",
            n_days=0, metrics={}, snapshots=[], trades=[], costs_detail={},
            data_ver="", duration_sec=time.time() - t0, status="error",
            error=str(e)
        )


def execute_and_save(spec: RunSpec, run_id: str | None = None) -> str:
    """Execute and persist to research.db in one call. Returns run_id."""
    from research.store import save_run
    import hashlib
    import json
    from core.strategies.registry import get_params

    result = execute(spec, run_id)
    if result.status == "done":
        # 计算生效参数（注册中心默认 + spec 覆盖）
        effective_params = {**get_params(spec.strategy), **(spec.params or {})}
        params_hash = hashlib.md5(
            json.dumps(effective_params, sort_keys=True).encode()
        ).hexdigest()[:8]
        
        save_run(
            run_id=result.run_id, strategy=spec.strategy, label=result.strategy_label,
            mode=spec.mode, params=effective_params, params_hash=params_hash,
            window_start=result.window_start, window_end=result.window_end, n_days=result.n_days,
            pool=spec.pool,             rebalance_days=spec.rebalance_days if spec.rebalance_days is not None else get_spec(spec.strategy).rebalance_days,
            max_positions=spec.max_positions if spec.max_positions is not None else get_spec(spec.strategy).max_positions,
            cost=spec.costs.to_dict(), data_ver=result.data_ver, kind=spec.kind,
            parent_sweep_id=spec.parent_sweep_id, tag=spec.tag, note=spec.note,
            metrics=result.metrics, equity=result.snapshots, trades=result.trades,
            duration_sec=result.duration_sec, status=result.status
        )
    else:
        save_run(run_id=result.run_id, strategy=spec.strategy, status="error",
                 note=result.error or "unknown error", window_start=result.window_start,
                 window_end=result.window_end, pool=spec.pool,
                 rebalance_days=0, max_positions=0, duration_sec=result.duration_sec)
    return result.run_id
