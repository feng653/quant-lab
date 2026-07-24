"""
SQLite trade database — every simulated trade and daily equity snapshot.

Tables:
  trades         — one row per executed order (both sizing modes)
  daily_snapshot — one row per strategy per mode per trading day

The DB is refreshed atomically on each pipeline run (full re-simulation of
the window), so it always matches the current strategy_state.json.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

DB_FILE = Path(__file__).resolve().parent.parent / "state" / "trades.db"
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    strategy TEXT NOT NULL,
    mode TEXT NOT NULL,
    code TEXT NOT NULL,
    action TEXT NOT NULL,
    shares INTEGER,
    price REAL,
    value REAL,
    commission REAL DEFAULT 0,
    stamp_duty REAL DEFAULT 0,
    slippage_cost REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS daily_snapshot (
    date TEXT NOT NULL,
    strategy TEXT NOT NULL,
    mode TEXT NOT NULL,
    equity REAL,
    cash REAL,
    n_positions INTEGER,
    daily_ret REAL,
    cum_ret REAL,
    bench_ret REAL,
    PRIMARY KEY (date, strategy, mode)
);
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy, mode);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(_SCHEMA)


def reset_run(strategies: list[str] | None = None) -> None:
    """Clear rows before a full re-simulation (all or selected strategies)."""
    init_db()
    with connect() as conn:
        if strategies is None:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM daily_snapshot")
        else:
            ph = ",".join("?" * len(strategies))
            conn.execute(f"DELETE FROM trades WHERE strategy IN ({ph})", strategies)
            conn.execute(f"DELETE FROM daily_snapshot WHERE strategy IN ({ph})", strategies)


def insert_trades(rows: list[dict]) -> None:
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            "INSERT INTO trades (date,strategy,mode,code,action,shares,price,value,commission,stamp_duty,slippage_cost)"
            " VALUES (:date,:strategy,:mode,:code,:action,:shares,:price,:value,:commission,:stamp_duty,:slippage_cost)",
            rows,
        )


def insert_snapshots(rows: list[dict]) -> None:
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO daily_snapshot (date,strategy,mode,equity,cash,n_positions,daily_ret,cum_ret,bench_ret)"
            " VALUES (:date,:strategy,:mode,:equity,:cash,:n_positions,:daily_ret,:cum_ret,:bench_ret)",
            rows,
        )


def get_trades(strategy: str | None = None, mode: str | None = None,
               date: str | None = None, limit: int = 5000) -> pd.DataFrame:
    q, cond, params = "SELECT * FROM trades", [], []
    if strategy:
        cond.append("strategy=?"); params.append(strategy)
    if mode:
        cond.append("mode=?"); params.append(mode)
    if date:
        cond.append("date=?"); params.append(date)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY date, strategy, id LIMIT ?"
    params.append(limit)
    with connect() as conn:
        return pd.read_sql(q, conn, params=params)


def get_snapshots(strategy: str | None = None, mode: str | None = None) -> pd.DataFrame:
    q, cond, params = "SELECT * FROM daily_snapshot", [], []
    if strategy:
        cond.append("strategy=?"); params.append(strategy)
    if mode:
        cond.append("mode=?"); params.append(mode)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY date"
    with connect() as conn:
        return pd.read_sql(q, conn, params=params)


def latest_date() -> str | None:
    with connect() as conn:
        r = conn.execute("SELECT MAX(date) FROM daily_snapshot").fetchone()
    return r[0] if r else None


def trade_dates() -> list[str]:
    with connect() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT date FROM daily_snapshot ORDER BY date")]
