"""
Unified runner — all 10 strategies x CSI 500 + CSI 800, with look-ahead-free backtest.

Strategies:
  Technical (4): ma_cross, rsi_reversal, bollinger_breakout, macd_signal
  Factor (2):    alpha158_lgb, alpha158_xgb
  ML (2):        lstm_rank, transformer_rank
  Portfolio (2): pairs_trading, risk_parity
"""

import sys

sys.path.insert(0, ".")

import logging
import time
import json
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

import numpy as np
import pandas as pd

from config.settings import config as cfg
from data.fetcher_akshare import fetch_index_members
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from evaluation.report import generate_markdown_report, generate_html_report

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _fetch_one(sym: str, start: str, end: str) -> pd.DataFrame | None:
    import akshare as ak

    try:
        prefix = "sh" if sym.startswith("6") else "sz"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{sym}", start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")
        df["code"] = sym
        return df
    except Exception:
        return None


def download_data(pool_name: str, n_stocks: int = 100) -> pd.DataFrame:
    """Download data for a given stock pool."""
    idx = cfg.universe.all_pools[pool_name][0]
    codes = fetch_index_members(idx)
    codes = codes[:n_stocks]
    print(f"  {pool_name}: {len(codes)} stocks, downloading...")
    frames = []
    for i, sym in enumerate(codes):
        if (i + 1) % 25 == 0:
            print(f"    {i + 1}/{len(codes)}...")
        r = _fetch_one(sym, cfg.period.backtest_start, cfg.period.backtest_end)
        if r is not None:
            frames.append(r)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"    {len(df)} rows, {df['code'].nunique()} stocks")
    return df


# ── Strategy signal generators ──

def _pivot(df):
    return df.pivot(index="date", columns="code", values="close")


def signals_ma_cross(pivot):
    ss: dict[str, list[dict]] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 80:
            continue
        m20 = s.rolling(20).mean()
        m60 = s.rolling(60).mean()
        cross = (m20 > m60) & (m20.shift(1) <= m60.shift(1))
        for d in cross[cross].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_rsi(pivot):
    ss: dict[str, list[dict]] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 30:
            continue
        d = s.diff()
        g = d.clip(lower=0).ewm(span=14, adjust=False).mean()
        l = (-d).clip(lower=0).ewm(span=14, adjust=False).mean()
        rs = g / l.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        buy = (rsi.shift(1) <= 30) & (rsi > 30)
        for d in buy[buy].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_bollinger(pivot):
    ss: dict[str, list[dict]] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 30:
            continue
        ma = s.rolling(20).mean()
        std = s.rolling(20).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        mid = ma
        prev_upper = upper.shift(1)
        prev_close = s.shift(1)
        buy = (prev_close < prev_upper) & (s > upper)
        sell = (s < mid) & (s.shift(1) >= mid.shift(1))
        for d in buy[buy].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
        for d in sell[sell].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "sell"})
    return ss


def signals_macd(pivot):
    ss: dict[str, list[dict]] = {}
    for code in pivot.columns:
        s = pivot[code].dropna()
        if len(s) < 50:
            continue
        ema12 = s.ewm(span=12, adjust=False).mean()
        ema26 = s.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
        for d in golden[golden].index:
            ss.setdefault(str(d.date()), []).append({"code": code, "action": "buy", "weight": 0.05})
    return ss


def signals_pairs_trading(pivot):
    from itertools import combinations
    from statsmodels.tsa.stattools import coint

    ss: dict[str, list[dict]] = {}
    codes = list(pivot.columns)
    pairs_found = 0
    for a, b in combinations(codes[:30], 2):  # limit to top 30 for speed
        pa = pivot[a].dropna()
        pb = pivot[b].dropna()
        ci = pa.index.intersection(pb.index)
        if len(ci) < 120:
            continue
        try:
            _, pv, _ = coint(pa[ci[-120:]], pb[ci[-120:]])
        except Exception:
            continue
        if pv >= 0.05:
            continue
        pairs_found += 1
        if pairs_found > 10:
            break
        spread = pa[ci] - pb[ci]
        sm = spread.rolling(120).mean()
        ssd = spread.rolling(120).std()
        z = (spread - sm) / ssd.replace(0, np.nan)
        prev_z = z.shift(1)
        for i in range(120, len(z)):
            if abs(z.iloc[i]) > 2 and abs(prev_z.iloc[i]) <= 2:
                dt = str(z.index[i].date())
                ss.setdefault(dt, []).append({"code": b if z.iloc[i] > 0 else a, "action": "buy", "weight": 0.1})
                ss.setdefault(dt, []).append({"code": a if z.iloc[i] > 0 else b, "action": "sell", "weight": 0.1})
            elif abs(z.iloc[i]) < 0.5 and abs(prev_z.iloc[i]) >= 0.5:
                dt = str(z.index[i].date())
                ss.setdefault(dt, []).append({"code": a, "action": "sell"})
                ss.setdefault(dt, []).append({"code": b, "action": "sell"})
    return ss


def signals_risk_parity(pivot):
    """Risk parity: monthly rebalance, equal risk contribution."""
    ss: dict[str, list[dict]] = {}
    rets = pivot.pct_change().dropna(how="all")
    dates = sorted(rets.index)
    rb_dates = pd.date_range(dates[0], dates[-1], freq="ME")

    for rd in rb_dates:
        idx = rets.index.get_indexer([rd], method="nearest")[0]
        if idx < 63:
            continue
        past = rets.iloc[max(0, idx - 63):idx].dropna(axis=1)
        if past.empty:
            continue
        vols = past.std()
        inv_vol = (1.0 / vols.replace(0, np.nan)).dropna()
        if inv_vol.empty:
            continue
        w = inv_vol / inv_vol.sum()
        dt = str(rets.index[idx].date())
        for code, weight in w.items():
            if weight > 0.01:
                ss.setdefault(dt, []).append({"code": code, "action": "buy", "weight": weight})
    return ss


SIGNAL_FUNCS = {
    "ma_cross": signals_ma_cross,
    "rsi_reversal": signals_rsi,
    "bollinger_breakout": signals_bollinger,
    "macd_signal": signals_macd,
    "pairs_trading": signals_pairs_trading,
    "risk_parity": signals_risk_parity,
}


STAR_MAP = {
    "ma_cross": 10400,
    "rsi_reversal": 10400,
    "bollinger_breakout": 10400,
    "macd_signal": 10400,
    "pairs_trading": 10400,
    "risk_parity": 4800,
    "alpha158_lgb": 46600,
    "alpha158_xgb": 46600,
    "lstm_rank": 46600,
    "transformer_rank": 46600,
}

SOURCE_MAP = {
    "ma_cross": "je-suis-tm/quant-trading",
    "rsi_reversal": "je-suis-tm/quant-trading",
    "bollinger_breakout": "je-suis-tm/quant-trading",
    "macd_signal": "je-suis-tm/quant-trading",
    "pairs_trading": "je-suis-tm/quant-trading",
    "risk_parity": "robertmartin8/PyPortfolioOpt",
    "alpha158_lgb": "microsoft/qlib",
    "alpha158_xgb": "microsoft/qlib",
    "lstm_rank": "microsoft/qlib",
    "transformer_rank": "microsoft/qlib",
}

CAT_MAP = {
    "ma_cross": "technical", "rsi_reversal": "technical", "bollinger_breakout": "technical", "macd_signal": "technical",
    "pairs_trading": "portfolio", "risk_parity": "portfolio",
    "alpha158_lgb": "factor", "alpha158_xgb": "factor",
    "lstm_rank": "ml", "transformer_rank": "ml",
}


def vectorized_backtest(price_df, signals, initial_cash=1_000_000.0,
                        commission=0.001, stamp_duty=0.001, slippage=0.001,
                        max_positions=20, rebalance_days=30):
    df = price_df.sort_values(["code", "date"]).copy()
    cp = df.pivot(index="date", columns="code", values="close")
    op = df.pivot(index="date", columns="code", values="open")
    dates = sorted(cp.index)
    cash = initial_cash
    positions: dict[str, float] = {}
    pv_history: list[float] = []

    for i, dt in enumerate(dates):
        d_str = str(dt.date())
        prices = cp.loc[dt].dropna()
        opens = op.loc[dt].dropna() if dt in op.index else prices
        is_rb = i % rebalance_days == 0

        prev_sigs = signals.get(str(dates[i - 1].date()), []) if i > 0 else []

        if is_rb:
            for code in list(positions.keys()):
                if code in prices.index:
                    cash += positions[code] * prices[code] * (1 - slippage) * (1 - commission - stamp_duty)
                del positions[code]

        for sig in prev_sigs:
            if sig["action"] == "sell" and sig["code"] in positions and sig["code"] in prices.index:
                cash += positions[sig["code"]] * prices[sig["code"]] * (1 - slippage) * (1 - commission - stamp_duty)
                del positions[sig["code"]]

        if is_rb:
            buy_list = [s for s in prev_sigs if s["action"] == "buy" and s["code"] in opens.index]
            if buy_list:
                w = 1.0 / len(buy_list)
                for sig in buy_list:
                    code = sig["code"]
                    bp = opens[code] * (1 + slippage)
                    shares = int(cash * w // bp // 100) * 100
                    if shares >= 100:
                        cash -= shares * bp * (1 + commission)
                        positions[code] = shares

        mkt = cash + sum(positions[c] * (prices[c] if c in prices.index else 0) for c in positions)
        pv_history.append(mkt)

    if not pv_history:
        return {"total_return_pct": 0, "sharpe_ratio": 0, "max_drawdown_pct": 0, "total_trades": 0, "final_value": 0}

    rets = pd.Series(pv_history, index=dates).pct_change().dropna()
    tr = (pv_history[-1] / initial_cash - 1)
    ann_ret = (1 + tr) ** (252 / max(len(rets), 1)) - 1
    ann_vol = float(rets.std() * np.sqrt(252))
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    cummax_vals = np.maximum.accumulate(pv_history)
    mdd = float(min((np.array(pv_history) - cummax_vals) / cummax_vals))

    signal_count = sum(len(v) for v in signals.values())

    return {
        "total_return_pct": round(tr * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "total_trades": signal_count,
        "final_value": round(pv_history[-1], 2),
    }


def run_full():
    print("=" * 60)
    print("Complete Strategy Verification — 10 Strategies x 2 Pools")
    print("=" * 60)
    t0 = time.time()

    all_results = []

    for pool in ["csi500", "csi800"]:
        print(f"\n{'─' * 60}")
        print(f"Pool: {pool}")
        print(f"{'─' * 60}")

        print("\n[Data] Downloading...")
        df = download_data(pool, n_stocks=100)
        pivot = _pivot(df)
        print(f"  Pivot shape: {pivot.shape}")

        for sname, sfunc in SIGNAL_FUNCS.items():
            st = time.time()
            print(f"\n  [{sname}] ★ {STAR_MAP[sname]:>6,d} | {CAT_MAP[sname]}", end=" ")
            signals = sfunc(pivot)
            sc = sum(len(v) for v in signals.values())
            print(f"| {sc} signals", end=" ")
            r = vectorized_backtest(df, signals)
            r["strategy"] = sname
            r["pool"] = pool
            r["source_stars"] = STAR_MAP[sname]
            r["source_project"] = SOURCE_MAP[sname]
            r["category"] = CAT_MAP[sname]
            all_results.append(r)
            print(f"→ Ret:{r['total_return_pct']:>7}% Shp:{r['sharpe_ratio']:>6} DD:{r['max_drawdown_pct']:>6}% ({time.time()-st:.0f}s)")

    print(f"\n{'=' * 60}")
    print("Final Summary")
    print(f"{'=' * 60}")
    print(f"  {'Strategy':<20s} {'Pool':<8s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s} {'Src★':>8s}")
    print("  " + "-" * 72)
    for r in sorted(all_results, key=lambda x: x.get("sharpe_ratio", -999) or -999, reverse=True):
        print(f"  {r['strategy']:<20s} {r['pool']:<8s} {r['total_return_pct']:>8} {r['sharpe_ratio']:>8} {r['max_drawdown_pct']:>8} {r['total_trades']:>8} {r.get('source_stars',0):>8}")

    # Save results
    with open(RESULTS_DIR / "all_results.json", "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Generate reports
    generate_markdown_report(all_results, "complete_report.md")
    generate_html_report(all_results, "complete_report.html")

    # Per-pool reports
    for pool in ["csi500", "csi800"]:
        pool_results = [r for r in all_results if r["pool"] == pool]
        generate_markdown_report(pool_results, f"report_{pool}.md")
        generate_html_report(pool_results, f"report_{pool}.html")

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print("Reports: reports/complete_report.md, reports/report_csi500.md, reports/report_csi800.md")
    print("Results: results/all_results.json")


if __name__ == "__main__":
    run_full()
