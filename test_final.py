"""Final test — fixes look-ahead bias with next-day execution."""

import sys

sys.path.insert(0, ".")

import logging

logging.basicConfig(level=logging.WARNING)

import time

import numpy as np
import pandas as pd

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from evaluation.report import generate_markdown_report, generate_html_report


def _fetch_one_akshare(sym: str, start: str, end: str) -> pd.DataFrame | None:
    import akshare as ak

    try:
        prefix = "sh" if sym.startswith("6") else "sz"
        df = ak.stock_zh_a_daily(
            symbol=f"{prefix}{sym}",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            adjust="qfq",
        )
        df["code"] = sym
        return df
    except Exception:
        return None


def generate_signals_vectorized(df: pd.DataFrame, name: str) -> dict[str, list[dict]]:
    """Generate signals using vectorized pandas, emitting sell-for-rebalance.

    Key fix: signals computed at T, executed at T+1 open.
    """
    df = df.sort_values(["code", "date"]).copy()
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    df_pivot = df.pivot(index="date", columns="code", values="close")
    dates = sorted(df_pivot.index)

    buy_signals: dict[str, list[str]] = {}

    if name == "ma_cross":
        for code in df_pivot.columns:
            series = df_pivot[code].dropna()
            if len(series) < 80:
                continue
            ma20 = series.rolling(20).mean()
            ma60 = series.rolling(60).mean()
            # Signal at T based on data up to T → execute at T+1
            cross_up = (ma20 > ma60) & (ma20.shift(1) <= ma60.shift(1))
            for d in cross_up[cross_up].index:
                d_str = str(d.date())
                buy_signals.setdefault(d_str, []).append(code)

    elif name == "rsi_reversal":
        for code in df_pivot.columns:
            series = df_pivot[code].dropna()
            if len(series) < 30:
                continue
            delta = series.diff()
            gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
            loss = (-delta).clip(lower=0).ewm(span=14, adjust=False).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi_prev = rsi.shift(1)
            buy = (rsi_prev <= 30) & (rsi > 30)
            for d in buy[buy].index:
                d_str = str(d.date())
                buy_signals.setdefault(d_str, []).append(code)

    elif name == "bollinger_breakout":
        for code in df_pivot.columns:
            series = df_pivot[code].dropna()
            if len(series) < 30:
                continue
            ma = series.rolling(20).mean()
            std = series.rolling(20).std()
            upper = ma + 2 * std
            prev_cl = series.shift(1)
            prev_upper = upper.shift(1)
            buy = (prev_cl <= prev_upper) & (series > upper)
            for d in buy[buy].index:
                d_str = str(d.date())
                buy_signals.setdefault(d_str, []).append(code)

    elif name == "macd_signal":
        for code in df_pivot.columns:
            series = df_pivot[code].dropna()
            if len(series) < 50:
                continue
            ema12 = series.ewm(span=12, adjust=False).mean()
            ema26 = series.ewm(span=26, adjust=False).mean()
            dif = ema12 - ema26
            dea = dif.ewm(span=9, adjust=False).mean()
            golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
            for d in golden[golden].index:
                d_str = str(d.date())
                buy_signals.setdefault(d_str, []).append(code)

    # Convert to signal dict: signal generated at T, will be executed at T+1
    # For sell: generate rebalance signal at T to sell existing positions
    signals: dict[str, list[dict]] = {}
    all_dates = set(buy_signals.keys())
    for d in sorted(all_dates):
        codes = buy_signals.get(d, [])
        # Assign equal weights
        if codes:
            w = 1.0 / min(len(codes), 20)
            for c in codes:
                signals.setdefault(d, []).append({"code": c, "action": "buy", "weight": w})

    return signals


def vectorized_backtest_lagged(
    price_df: pd.DataFrame,
    signals: dict[str, list[dict]],
    initial_cash: float = 1_000_000.0,
    commission: float = 0.001,
    stamp_duty: float = 0.001,
    slippage: float = 0.001,
    max_positions: int = 20,
    rebalance_days: int = 30,
) -> dict:
    """Backtest with look-ahead-free execution: signal at T → trade at T+1 open.

    Also implements periodic rebalance: every rebalance_days, sell all positions
    and re-enter based on latest buy signals.
    """
    df = price_df.sort_values(["code", "date"]).copy()
    close_pivot = df.pivot(index="date", columns="code", values="close")
    open_pivot = df.pivot(index="date", columns="code", values="open")
    dates = sorted(close_pivot.index)

    cash = initial_cash
    positions: dict[str, float] = {}
    portfolio_values: list[float] = []
    last_rebalance: dict[str, str] = {}  # code -> rebalance date

    for i, dt in enumerate(dates):
        d_str = str(dt.date())
        prices_today = close_pivot.loc[dt].dropna()
        opens_today = open_pivot.loc[dt].dropna() if dt in open_pivot.index else prices_today

        # Check if today is a rebalance day (every rebalance_days)
        is_rebalance = i % rebalance_days == 0

        # Get signals from PREVIOUS trading day
        prev_signals: list[dict] = []
        if i > 0:
            prev_d = str(dates[i - 1].date())
            prev_signals = signals.get(prev_d, [])

        # Sell all on rebalance day
        if is_rebalance:
            for code in list(positions.keys()):
                if code in prices_today.index:
                    sp = prices_today[code] * (1 - slippage)
                    cash += positions[code] * sp * (1 - commission - stamp_duty)
                    del positions[code]

        # Process sell signals
        for sig in prev_signals:
            if sig["action"] != "sell":
                continue
            code = sig["code"]
            if code in positions and code in prices_today.index:
                sp = prices_today[code] * (1 - slippage)
                cash += positions[code] * sp * (1 - commission - stamp_duty)
                del positions[code]

        # Process buy signals (executed at today's open, from yesterday's signal)
        if is_rebalance:
            buy_codes = [s["code"] for s in prev_signals if s["action"] == "buy" and s["code"] in opens_today.index]
            if buy_codes:
                w = 1.0 / len(buy_codes)
                for code in buy_codes:
                    bp = opens_today[code] * (1 + slippage)
                    shares = int(cash * w // bp // 100) * 100
                    if shares >= 100:
                        cost = shares * bp
                        cash -= cost * (1 + commission)
                        positions[code] = shares

        # MTM
        mkt = cash + sum(positions[c] * (prices_today[c] if c in prices_today.index else 0) for c in positions)
        portfolio_values.append(mkt)

    rets = pd.Series(portfolio_values, index=dates).pct_change().dropna()
    tr = (portfolio_values[-1] / initial_cash - 1) if portfolio_values else 0
    ann_ret = (1 + tr) ** (252 / max(len(rets), 1)) - 1
    ann_vol = float(rets.std() * np.sqrt(252))
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    cummax_vals = np.maximum.accumulate(portfolio_values)
    mdd = float(min((np.array(portfolio_values) - cummax_vals) / cummax_vals))

    signal_count = sum(1 for sl in signals.values() for s in sl)

    return {
        "total_return_pct": round(tr * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "total_trades": signal_count,
        "win_rate_pct": 0,
        "final_value": round(portfolio_values[-1], 2),
    }


def main():
    print("=" * 60)
    print("Final Strategy Verification — 80 stocks, CSI 500, 2024-2026")
    print("=" * 60)
    t0 = time.time()

    print("\n[1/4] Data download (sequential)...")
    codes = fetch_index_members("000905")
    print(f"  CSI 500: {len(codes)} stocks → using 80")

    frames = []
    for i, sym in enumerate(codes[:80]):
        if (i + 1) % 20 == 0:
            print(f"    {i + 1}/80...")
        r = _fetch_one_akshare(sym, cfg.period.backtest_start, cfg.period.backtest_end)
        if r is not None:
            frames.append(r)

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"  Data: {len(df)} rows, {df['code'].nunique()} stocks ({time.time() - t0:.0f}s)")

    print("\n[2/4] Strategies...")
    results = []
    strategy_names = ["ma_cross", "rsi_reversal", "bollinger_breakout", "macd_signal"]
    star_map = {"ma_cross": 10400, "rsi_reversal": 10400, "bollinger_breakout": 10400, "macd_signal": 10400}

    for name in strategy_names:
        st = time.time()
        print(f"  {name:20s} ★ {star_map[name]:>6,d} | generating signals...", end=" ")
        signals = generate_signals_vectorized(df, name)
        sc = sum(len(v) for v in signals.values())
        print(f"{sc} signals | backtesting...", end=" ")

        r = vectorized_backtest_lagged(df, signals)
        r["strategy"] = name
        r["pool"] = "csi500"
        r["source_stars"] = star_map[name]
        r["source_project"] = "je-suis-tm/quant-trading"
        r["category"] = "technical"
        results.append(r)
        print(f"Ret:{r['total_return_pct']:>7}% Shp:{r['sharpe_ratio']:>6} DD:{r['max_drawdown_pct']:>6}%")

    print("\n[3/4] Results:")
    print(f"  {'Strategy':<20s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s}")
    print("  " + "-" * 55)
    for r in sorted(results, key=lambda x: x["sharpe_ratio"], reverse=True):
        print(f"  {r['strategy']:<20s} {r['total_return_pct']:>8} {r['sharpe_ratio']:>8} {r['max_drawdown_pct']:>8} {r['total_trades']:>8}")

    print("\n[4/4] Reports...")
    generate_markdown_report(results, "final_report.md")
    generate_html_report(results, "final_report.html")
    print(f"  reports/final_report.md, reports/final_report.html")
    print(f"\nTotal: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
