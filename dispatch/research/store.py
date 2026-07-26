"""
Experiment store — append-only research database.

Physically isolated from the production ``trades.db``: production is a single
overwritten timeline, research is a multi-dimensional append-only experiment
space (strategy x params x window x cost x universe).

Schema notes:
  runs        one row per experiment (immutable once status='done')
  run_metrics long table (run_id, metric, value) so new metrics never need a
              schema migration
  run_equity  the equity curve, for overlay charts and re-derived statistics
  run_trades  executions, kept in full (a 2-year run is <2k rows)
  sweeps      parent record for a parameter grid; children link via
              runs.parent_sweep_id

Reproducibility: every run records ``data_version`` (hash of the price data it
consumed) and ``code_version`` (git HEAD), so a result can always be traced
back to the exact inputs that produced it.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "state" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'backtest',
    strategy        TEXT NOT NULL,
    label           TEXT,
    mode            TEXT NOT NULL DEFAULT 'equal',
    params_json     TEXT,
    window_start    TEXT,
    window_end      TEXT,
    n_days          INTEGER,
    pool            TEXT,
    rebalance_days  INTEGER,
    max_positions   INTEGER,
    cost_json       TEXT,
    data_version    TEXT,
    code_version    TEXT,
    parent_sweep_id TEXT,
    tag             TEXT,
    note            TEXT,
    status          TEXT NOT NULL DEFAULT 'done',
    duration_sec    REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_strategy ON runs(strategy);
CREATE INDEX IF NOT EXISTS idx_runs_created  ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_sweep    ON runs(parent_sweep_id);
CREATE INDEX IF NOT EXISTS idx_runs_tag      ON runs(tag);

CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value  REAL,
    PRIMARY KEY (run_id, metric)
);

CREATE TABLE IF NOT EXISTS run_equity (
    run_id TEXT NOT NULL,
    date   TEXT NOT NULL,
    equity REAL,
    cash   REAL,
    n_positions INTEGER,
    daily_ret REAL,
    bench_ret REAL,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE IF NOT EXISTS run_trades (
    run_id   TEXT NOT NULL,
    date     TEXT,
    code     TEXT,
    action   TEXT,
    shares   INTEGER,
    price    REAL,
    value    REAL,
    commission REAL,
    stamp_duty REAL,
    slippage_cost REAL
);
CREATE INDEX IF NOT EXISTS idx_trades_run ON run_trades(run_id);

CREATE TABLE IF NOT EXISTS sweeps (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    base_strategy TEXT,
    grid_json     TEXT,
    objective     TEXT,
    window_start  TEXT,
    window_end    TEXT,
    pool          TEXT,
    n_children    INTEGER DEFAULT 0,
    note          TEXT,
    status        TEXT DEFAULT 'running'
);
"""


@contextmanager
def connect():
    """Connection with row access by name. WAL for concurrent read during runs."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
    logger.info("research.db ready at %s", DB_PATH)


def code_version() -> str:
    """Current git HEAD (short). Empty string outside a repo."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=str(Path(__file__).resolve().parent.parent.parent))
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def data_version(df) -> str:
    """Cheap fingerprint of the input data: rows|codes|last_date."""
    try:
        if df is None or len(df) == 0:
            return "empty"
        return f"{len(df)}|{df['code'].nunique()}|{str(df['date'].max())[:10]}"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────
# writes
# ─────────────────────────────────────────────────────────────────

def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def save_run(*, run_id: str | None = None, strategy: str, label: str = "",
             mode: str = "equal", params: dict | None = None,
             window_start: str = "", window_end: str = "", n_days: int = 0,
             pool: str = "csi500", rebalance_days: int = 30, max_positions: int = 20,
             cost: dict | None = None, data_ver: str = "", kind: str = "backtest",
             parent_sweep_id: str | None = None, tag: str = "", note: str = "",
             metrics: dict | None = None, equity: Iterable[dict] | None = None,
             trades: Iterable[dict] | None = None, duration_sec: float = 0.0,
             status: str = "done") -> str:
    """Persist a complete run. Returns the run id."""
    rid = run_id or new_run_id()
    with connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO runs
              (id, created_at, kind, strategy, label, mode, params_json,
               window_start, window_end, n_days, pool, rebalance_days,
               max_positions, cost_json, data_version, code_version,
               parent_sweep_id, tag, note, status, duration_sec)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (rid, datetime.now().isoformat(timespec="seconds"), kind, strategy,
              label, mode, json.dumps(params or {}, ensure_ascii=False),
              window_start, window_end, n_days, pool, rebalance_days,
              max_positions, json.dumps(cost or {}), data_ver, code_version(),
              parent_sweep_id, tag, note, status, round(duration_sec, 2)))

        if metrics:
            conn.executemany(
                "INSERT OR REPLACE INTO run_metrics(run_id, metric, value) VALUES (?,?,?)",
                [(rid, k, float(v)) for k, v in metrics.items()
                 if v is not None and isinstance(v, (int, float))])

        if equity:
            conn.executemany("""
                INSERT OR REPLACE INTO run_equity
                  (run_id, date, equity, cash, n_positions, daily_ret, bench_ret)
                VALUES (?,?,?,?,?,?,?)
            """, [(rid, s.get("date"), s.get("equity"), s.get("cash"),
                   s.get("n_positions"), s.get("daily_ret"), s.get("bench_ret"))
                  for s in equity])

        if trades:
            conn.execute("DELETE FROM run_trades WHERE run_id=?", (rid,))
            conn.executemany("""
                INSERT INTO run_trades
                  (run_id, date, code, action, shares, price, value,
                   commission, stamp_duty, slippage_cost)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, [(rid, t.get("date"), t.get("code"), t.get("action"),
                   t.get("shares"), t.get("price"), t.get("value"),
                   t.get("commission"), t.get("stamp_duty"), t.get("slippage_cost"))
                  for t in trades])
    return rid


def create_sweep(*, base_strategy: str, grid: dict, objective: str = "sharpe",
                 window_start: str = "", window_end: str = "", pool: str = "csi500",
                 note: str = "") -> str:
    sid = uuid.uuid4().hex[:12]
    with connect() as conn:
        conn.execute("""
            INSERT INTO sweeps (id, created_at, base_strategy, grid_json, objective,
                                window_start, window_end, pool, note, status)
            VALUES (?,?,?,?,?,?,?,?,?,'running')
        """, (sid, datetime.now().isoformat(timespec="seconds"), base_strategy,
              json.dumps(grid, ensure_ascii=False), objective,
              window_start, window_end, pool, note))
    return sid


def finish_sweep(sweep_id: str, n_children: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE sweeps SET status='done', n_children=? WHERE id=?",
                     (n_children, sweep_id))


def delete_run(run_id: str) -> None:
    with connect() as conn:
        for t in ("run_metrics", "run_equity", "run_trades"):
            conn.execute(f"DELETE FROM {t} WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id=?", (run_id,))


def set_run_fields(run_id: str, **fields) -> None:
    """Update mutable annotation fields (tag, note)."""
    allowed = {"tag", "note", "status"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    clause = ", ".join(f"{k}=?" for k in sets)
    with connect() as conn:
        conn.execute(f"UPDATE runs SET {clause} WHERE id=?",
                     (*sets.values(), run_id))


# ─────────────────────────────────────────────────────────────────
# reads
# ─────────────────────────────────────────────────────────────────

METRIC_COLUMNS = ["total_return", "annual_return", "sharpe", "sortino", "calmar",
                  "max_dd", "volatility", "win_rate", "n_trades", "turnover_ratio",
                  "alpha", "beta", "info_ratio", "sharpe_t_stat"]


def list_runs(*, strategy: str = "", tag: str = "", kind: str = "",
              sweep_id: str = "", pool: str = "", limit: int = 300,
              order_by: str = "created_at", desc: bool = True) -> list[dict]:
    """Runs joined with their metrics pivoted into columns, for the leaderboard."""
    where, args = ["1=1"], []
    if strategy:
        where.append("r.strategy=?"); args.append(strategy)
    if tag:
        where.append("r.tag=?"); args.append(tag)
    if kind:
        where.append("r.kind=?"); args.append(kind)
    if pool:
        where.append("r.pool=?"); args.append(pool)
    if sweep_id:
        where.append("r.parent_sweep_id=?"); args.append(sweep_id)

    pivots = ",\n".join(
        f"MAX(CASE WHEN m.metric='{c}' THEN m.value END) AS {c}"
        for c in METRIC_COLUMNS)

    sort_col = order_by if order_by in METRIC_COLUMNS + ["created_at", "strategy"] else "created_at"
    direction = "DESC" if desc else "ASC"
    # metric sorts must push NULLs last so incomplete runs never top the board
    order_sql = (f"r.{sort_col} {direction}" if sort_col in ("created_at", "strategy")
                 else f"{sort_col} IS NULL, {sort_col} {direction}")

    sql = f"""
        SELECT r.*, {pivots}
        FROM runs r LEFT JOIN run_metrics m ON m.run_id = r.id
        WHERE {' AND '.join(where)}
        GROUP BY r.id
        ORDER BY {order_sql}
        LIMIT ?
    """
    args.append(limit)
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_run(run_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        run = dict(row)
        run["params"] = json.loads(run.get("params_json") or "{}")
        run["cost"] = json.loads(run.get("cost_json") or "{}")
        run["metrics"] = {r["metric"]: r["value"] for r in conn.execute(
            "SELECT metric, value FROM run_metrics WHERE run_id=?", (run_id,))}
        return run


def get_equity(run_id: str) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT date, equity, cash, n_positions, daily_ret, bench_ret "
            "FROM run_equity WHERE run_id=? ORDER BY date", (run_id,))]


def get_trades(run_id: str, limit: int = 5000) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM run_trades WHERE run_id=? ORDER BY date, action LIMIT ?",
            (run_id, limit))]


def get_sweep(sweep_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM sweeps WHERE id=?", (sweep_id,)).fetchone()
        if row is None:
            return None
        sw = dict(row)
        sw["grid"] = json.loads(sw.get("grid_json") or "{}")
        return sw


def list_sweeps(limit: int = 100) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM sweeps ORDER BY created_at DESC LIMIT ?", (limit,))]


def distinct_values(column: str) -> list[str]:
    """Distinct non-empty values of a runs column, for filter dropdowns."""
    if column not in ("strategy", "tag", "kind", "pool", "mode"):
        return []
    with connect() as conn:
        return [r[0] for r in conn.execute(
            f"SELECT DISTINCT {column} FROM runs WHERE {column} IS NOT NULL "
            f"AND {column}!='' ORDER BY {column}")]


def stats() -> dict:
    """Counters for the research landing page."""
    with connect() as conn:
        one = lambda q: conn.execute(q).fetchone()[0]
        return {"n_runs": one("SELECT COUNT(*) FROM runs"),
                "n_sweeps": one("SELECT COUNT(*) FROM sweeps"),
                "n_strategies": one("SELECT COUNT(DISTINCT strategy) FROM runs"),
                "n_trades": one("SELECT COUNT(*) FROM run_trades")}


# how many distinct configurations have been evaluated — the multiple-testing
# count that deflated Sharpe needs
def trial_count(strategy: str = "") -> int:
    with connect() as conn:
        if strategy:
            return conn.execute(
                "SELECT COUNT(DISTINCT params_json) FROM runs WHERE strategy=?",
                (strategy,)).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]


init_db()
