"""
Simulation runner — orchestrates the full daily simulation pipeline.

Every run: update data → regenerate signals → re-simulate the whole window
(deterministic, idempotent) → refresh SQLite → write strategy_state.json.

simulation_start is fixed at first setup (two months before first run) and
never moves afterwards; cumulative return therefore starts from a stable,
explicitly-labeled origin.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from services import trade_db
from services.data_service import auto_update, trading_days, load_pool
from services.market_service import benchmark_window, classify_market
from services.signal_service import ALL_STRATEGIES, STRATEGY_META, generate_all_signals
from services.sim_engine import INITIAL_CASH, MODES, simulate_strategy, summary_metrics

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
STATE_FILE = STATE_DIR / "strategy_state.json"
POOL = "csi500"


def _default_sim_start() -> str:
    """First trading day on/after (today - 2 calendar months)."""
    target = (pd.Timestamp.now() - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    days = trading_days(target, today)
    return days[0] if days else target


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def get_sim_start() -> str:
    st = load_state()
    return st.get("meta", {}).get("simulation_start") or _default_sim_start()


def run_simulation(strategies: list[str] | None = None, update_data: bool = True) -> dict:
    """Full pipeline. Returns context for email builders and the dashboard."""
    strategies = strategies or ALL_STRATEGIES

    # 1) data
    if update_data:
        df, latest, added = auto_update(POOL)
    else:
        df = load_pool(POOL)
        latest = df["date"].max().strftime("%Y-%m-%d") if not df.empty else ""
    if df.empty:
        raise RuntimeError("No data available")
    pivot = df.pivot(index="date", columns="code", values="close")
    logger.info("Pivot: %d days × %d codes, latest %s", *pivot.shape, pivot.index[-1].date())

    # 2) simulation window
    sim_start = get_sim_start()
    sim_dates = [d for d in pivot.index if d >= pd.Timestamp(sim_start)]
    if not sim_dates:
        raise RuntimeError(f"No trading days on/after simulation_start {sim_start}")
    logger.info("Simulation window: %s → %s (%d days)", sim_start, sim_dates[-1].date(), len(sim_dates))

    # 3) signals (all 10 strategies; ML cached across runs)
    all_sigs = generate_all_signals(pivot, sim_start, strategies)

    # 4) benchmark
    bench = benchmark_window(sim_start)
    bench_start_val = float(bench.iloc[0]) if len(bench) else None

    # 5) simulate
    trade_db.reset_run(strategies)
    state = {"meta": {"simulation_start": sim_start, "pool": POOL,
                      "initial_cash": INITIAL_CASH, "modes": list(MODES),
                      "updated": datetime.now().isoformat()},
             "strategies": {}}

    for sn in strategies:
        sigs = all_sigs.get(sn, {})
        logger.info("Simulating %s (%d signal days)...", sn, len(sigs))
        res = simulate_strategy(pivot, sigs, sn, sim_dates,
                                bench_start=bench_start_val, benchmark=bench)
        entry = {"label": STRATEGY_META[sn]["label"], "cat": STRATEGY_META[sn]["cat"],
                 "desc": STRATEGY_META[sn]["desc"]}
        for mode in MODES:
            r = res[mode]
            trade_db.insert_trades(r["trades"])
            trade_db.insert_snapshots(r["snapshots"])
            m = summary_metrics(r["snapshots"])
            entry[mode] = {
                **m, "costs": r["costs"],
                "final_equity": r["final_equity"], "cash": r["cash"],
                "positions": {str(k): int(v) for k, v in r["positions"].items()},
                "dates": [s["date"] for s in r["snapshots"]],
                "equity": [s["equity"] for s in r["snapshots"]],
                "bench_ret": round((bench.iloc[-1] / bench_start_val - 1) * 100, 2) if bench_start_val else 0,
            }
        state["strategies"][sn] = entry

    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))
    logger.info("State saved: %s", STATE_FILE)

    return {"sim_start": sim_start, "latest_date": str(sim_dates[-1].date()),
            "n_days": len(sim_dates), "state": state, "benchmark": bench,
            "market": classify_market(), "signals": all_sigs, "pivot": pivot,
            "df": df}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ctx = run_simulation()
    for sn, e in ctx["state"]["strategies"].items():
        eq = e["equal"]; ad = e["adaptive"]
        print(f"{e['label']:<10s} equal {eq['total_return']:+7.2f}% (Sharpe {eq['sharpe']:+.2f}) | "
              f"adaptive {ad['total_return']:+7.2f}% (Sharpe {ad['sharpe']:+.2f}) | bench {eq['bench_ret']:+.2f}%")
