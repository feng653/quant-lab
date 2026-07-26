"""
Full metrics suite.

The production summary in ``kernel/sim_engine.summary_metrics`` reports 7
numbers, which is enough for a daily email but not enough to choose between
strategies. This module computes the full set used by the research pages.

Conventions
  - returns are daily, simple (not log)
  - annualization factor 252
  - risk-free rate 2% annual, matching the existing Sharpe definition
  - percentages are stored as percent (12.34 means 12.34%), ratios as ratios
  - every function tolerates short or degenerate input and returns 0.0 rather
    than raising, because sweep children can produce near-empty curves
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
RISK_FREE = 0.02
INITIAL_CASH = 1_000_000.0


def _safe(x, nd: int = 4) -> float:
    """Finite float or 0.0 — NaN/inf never reach the database."""
    try:
        v = float(x)
        return round(v, nd) if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


# ───────────────────────── return / risk ─────────────────────────

def total_return(equity: pd.Series, initial: float = INITIAL_CASH) -> float:
    if equity.empty:
        return 0.0
    return float(equity.iloc[-1] / initial - 1)


def annual_return(total_ret: float, n_days: int) -> float:
    years = max(n_days / TRADING_DAYS, 1 / TRADING_DAYS)
    base = 1 + total_ret
    if base <= 0:                      # total wipeout: CAGR undefined
        return -1.0
    return float(base ** (1 / years) - 1)


def volatility(rets: pd.Series) -> float:
    if len(rets) < 2:
        return 0.0
    return float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS))


def downside_volatility(rets: pd.Series, mar: float = 0.0) -> float:
    """Annualized std of returns below the minimum acceptable return."""
    if len(rets) < 2:
        return 0.0
    downside = rets[rets < mar]
    if len(downside) < 2:
        return 0.0
    return float(downside.std(ddof=1) * np.sqrt(TRADING_DAYS))


# Volatility below this is treated as zero. A curve that flat is degenerate
# (e.g. a sweep child that never traded); dividing by float noise would produce
# an astronomical Sharpe that then tops the leaderboard.
VOL_FLOOR = 1e-6


def sharpe(annual_ret: float, vol: float, rf: float = RISK_FREE) -> float:
    return float((annual_ret - rf) / vol) if vol > VOL_FLOOR else 0.0


def sortino(annual_ret: float, down_vol: float, rf: float = RISK_FREE) -> float:
    """Sharpe that only penalizes downside deviation."""
    return float((annual_ret - rf) / down_vol) if down_vol > VOL_FLOOR else 0.0


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    return float(((equity - peak) / peak).min())


def calmar(annual_ret: float, max_dd: float) -> float:
    """Annual return per unit of worst drawdown."""
    return float(annual_ret / abs(max_dd)) if max_dd < 0 else 0.0


def drawdown_stats(equity: pd.Series) -> dict:
    """Depth, and the duration/recovery profile of drawdowns in trading days."""
    if len(equity) < 2:
        return {"max_dd": 0.0, "max_dd_duration": 0, "current_dd": 0.0,
                "time_underwater_pct": 0.0}
    peak = equity.cummax()
    dd = (equity - peak) / peak
    underwater = dd < -1e-9

    longest = current = 0
    for flag in underwater:
        current = current + 1 if flag else 0
        longest = max(longest, current)

    return {"max_dd": float(dd.min()),
            "max_dd_duration": int(longest),
            "current_dd": float(dd.iloc[-1]),
            "time_underwater_pct": float(underwater.mean() * 100)}


def var_cvar(rets: pd.Series, level: float = 0.05) -> tuple[float, float]:
    """Historical daily VaR and conditional VaR (expected shortfall)."""
    if len(rets) < 20:
        return 0.0, 0.0
    var = float(np.quantile(rets, level))
    tail = rets[rets <= var]
    cvar = float(tail.mean()) if len(tail) else var
    return var, cvar


# ───────────────────────── benchmark-relative ─────────────────────────

def alpha_beta(rets: pd.Series, bench_rets: pd.Series,
               rf: float = RISK_FREE) -> tuple[float, float]:
    """OLS alpha (annualized) and beta against the benchmark."""
    aligned = pd.concat([rets, bench_rets], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0, 0.0
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    var_b = float(b.var(ddof=1))
    if var_b <= 0:
        return 0.0, 0.0
    beta = float(b.cov(r) / var_b)
    daily_rf = rf / TRADING_DAYS
    alpha_daily = float((r - daily_rf).mean() - beta * (b - daily_rf).mean())
    return alpha_daily * TRADING_DAYS, beta


def information_ratio(rets: pd.Series, bench_rets: pd.Series) -> float:
    """Annualized mean active return over its own volatility (tracking error)."""
    aligned = pd.concat([rets, bench_rets], axis=1).dropna()
    if len(aligned) < 20:
        return 0.0
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    te = float(active.std(ddof=1))
    if te <= 0:
        return 0.0
    return float(active.mean() / te * np.sqrt(TRADING_DAYS))


def capture_ratios(rets: pd.Series, bench_rets: pd.Series) -> dict:
    """Share of benchmark up-moves captured vs down-moves suffered."""
    aligned = pd.concat([rets, bench_rets], axis=1).dropna()
    if len(aligned) < 20:
        return {"up_capture": 0.0, "down_capture": 0.0}
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    up, down = b > 0, b < 0
    uc = float(r[up].mean() / b[up].mean()) if up.sum() > 5 and b[up].mean() != 0 else 0.0
    dc = float(r[down].mean() / b[down].mean()) if down.sum() > 5 and b[down].mean() != 0 else 0.0
    return {"up_capture": uc, "down_capture": dc}


# ───────────────────────── trading activity ─────────────────────────

def trade_stats(trades: list[dict], avg_equity: float) -> dict:
    """Counts, cost drag and turnover. Turnover is annualized one-way."""
    if not trades:
        return {"n_trades": 0, "n_buys": 0, "n_sells": 0, "total_cost": 0.0,
                "turnover_value": 0.0, "turnover_ratio": 0.0, "cost_drag_pct": 0.0}
    buys = [t for t in trades if t.get("action") == "buy"]
    sells = [t for t in trades if t.get("action") == "sell"]
    gross = sum(float(t.get("value") or 0) for t in trades)
    cost = sum(float(t.get("commission") or 0) + float(t.get("stamp_duty") or 0)
               + float(t.get("slippage_cost") or 0) for t in trades)
    return {"n_trades": len(trades), "n_buys": len(buys), "n_sells": len(sells),
            "total_cost": cost, "turnover_value": gross,
            "turnover_ratio": float(gross / avg_equity) if avg_equity > 0 else 0.0,
            "cost_drag_pct": float(cost / avg_equity * 100) if avg_equity > 0 else 0.0}


def win_loss_stats(rets: pd.Series) -> dict:
    """Daily hit rate and payoff profile."""
    if len(rets) < 2:
        return {"win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "profit_factor": 0.0, "best_day": 0.0, "worst_day": 0.0}
    wins, losses = rets[rets > 0], rets[rets < 0]
    gross_win, gross_loss = float(wins.sum()), abs(float(losses.sum()))
    # profit_factor: total gains / total losses. If no losing days but positive
    # gains, cap at 999.0 (means "no losses"); if no wins either, then 0.0.
    if gross_loss > 1e-9:
        pf = float(gross_win / gross_loss)
    elif gross_win > 1e-9:
        pf = 999.0
    else:
        pf = 0.0
    return {"win_rate": float((rets > 0).mean() * 100),
            "avg_win": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss": float(losses.mean()) if len(losses) else 0.0,
            "profit_factor": pf,
            "best_day": float(rets.max()), "worst_day": float(rets.min())}


# ───────────────────────── period breakdown ─────────────────────────

def monthly_returns(equity: pd.Series) -> dict[str, float]:
    """Calendar-month returns keyed YYYY-MM, in percent."""
    if len(equity) < 2:
        return {}
    monthly = equity.resample("ME").last()
    first = pd.Series([equity.iloc[0]], index=[equity.index[0]])
    chain = pd.concat([first, monthly]).drop_duplicates()
    rets = chain.pct_change(fill_method=None).dropna()
    return {d.strftime("%Y-%m"): _safe(v * 100, 2) for d, v in rets.items()}


def yearly_returns(equity: pd.Series) -> dict[str, float]:
    if len(equity) < 2:
        return {}
    yearly = equity.resample("YE").last()
    first = pd.Series([equity.iloc[0]], index=[equity.index[0]])
    chain = pd.concat([first, yearly]).drop_duplicates()
    rets = chain.pct_change(fill_method=None).dropna()
    return {d.strftime("%Y"): _safe(v * 100, 2) for d, v in rets.items()}


# ───────────────────────── aggregate ─────────────────────────

def full_metrics(snaps: list[dict], trades: list[dict] | None = None,
                 initial: float = INITIAL_CASH) -> dict:
    """Complete metric dictionary for one run.

    ``snaps`` are sim_engine snapshots (date/equity/daily_ret/bench_ret).
    Benchmark-relative metrics are computed only when bench_ret is populated.
    Percent-valued keys are suffixed conceptually (return/dd/vol/rate) and
    stored as percent; ratios (sharpe/beta/calmar) are stored raw.
    """
    if len(snaps) < 2:
        return {k: 0.0 for k in
                ("total_return", "annual_return", "sharpe", "sortino", "calmar",
                 "max_dd", "volatility", "win_rate", "n_trades")}

    idx = pd.to_datetime([s["date"] for s in snaps])
    equity = pd.Series([float(s["equity"]) for s in snaps], index=idx)
    rets = pd.Series([float(s.get("daily_ret") or 0) for s in snaps], index=idx).iloc[1:]

    tot = total_return(equity, initial)
    ann = annual_return(tot, len(equity))
    vol = volatility(rets)
    dvol = downside_volatility(rets)
    dd = drawdown_stats(equity)
    shp = sharpe(ann, vol)
    var, cvar = var_cvar(rets)

    out = {
        "total_return": _safe(tot * 100, 2),
        "annual_return": _safe(ann * 100, 2),
        "volatility": _safe(vol * 100, 2),
        "downside_vol": _safe(dvol * 100, 2),
        "sharpe": _safe(shp, 3),
        "sortino": _safe(sortino(ann, dvol), 3),
        "calmar": _safe(calmar(ann, dd["max_dd"]), 3),
        "max_dd": _safe(dd["max_dd"] * 100, 2),
        "max_dd_duration": dd["max_dd_duration"],
        "current_dd": _safe(dd["current_dd"] * 100, 2),
        "time_underwater_pct": _safe(dd["time_underwater_pct"], 1),
        "var_95": _safe(var * 100, 3),
        "cvar_95": _safe(cvar * 100, 3),
        "n_days": len(equity),
        "final_equity": _safe(equity.iloc[-1], 2),
        "today_return": _safe(rets.iloc[-1] * 100, 2) if len(rets) else 0.0,
    }
    out.update({k: _safe(v * 100 if k in ("avg_win", "avg_loss", "best_day", "worst_day")
                         else v, 3) for k, v in win_loss_stats(rets).items()})

    bench_cum = [float(s.get("bench_ret") or 0) for s in snaps]
    if any(abs(b) > 1e-12 for b in bench_cum):
        bench_curve = pd.Series([1 + b for b in bench_cum], index=idx)
        bench_rets = bench_curve.pct_change(fill_method=None).dropna()
        a, b = alpha_beta(rets, bench_rets)
        out["alpha"] = _safe(a * 100, 2)
        out["beta"] = _safe(b, 3)
        out["info_ratio"] = _safe(information_ratio(rets, bench_rets), 3)
        out["bench_return"] = _safe(bench_cum[-1] * 100, 2)
        out["excess_return"] = _safe((tot - bench_cum[-1]) * 100, 2)
        out.update({k: _safe(v, 3) for k, v in capture_ratios(rets, bench_rets).items()})

    if trades is not None:
        out.update({k: _safe(v, 2) for k, v in
                    trade_stats(trades, float(equity.mean())).items()})

    return out
