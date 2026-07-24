"""Optimized full test — parallel data download, 100 stocks, CSI 500."""

import sys

sys.path.insert(0, ".")

import logging

logging.basicConfig(level=logging.WARNING)

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members, _cache_path, _save_cache
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from backtest.engine import run_single_strategy
from evaluation.report import generate_markdown_report, generate_html_report


def _fetch_one_stock(sym: str, start: str, end: str) -> pd.DataFrame | None:
    """Fetch daily kline for a single stock via AKShare."""
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


def fetch_all_stocks_parallel(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Download all stocks in parallel using thread pool."""
    import hashlib

    cache_key = f"all_{start}_{end}"
    h = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    cache_file = _cache_path(cache_key + "_" + h)
    cache_file = cache_file.with_name(f"full_{h}.parquet")

    if cache_file.exists():
        return pd.read_parquet(cache_file)

    frames: list[pd.DataFrame] = []
    total = len(symbols)
    done = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one_stock, s, start, end): s for s in symbols}
        for future in as_completed(futures):
            done += 1
            if done % 50 == 0:
                print(f"    {done}/{total} stocks downloaded...")
            r = future.result()
            if r is not None:
                frames.append(r)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])
    _save_cache(f"full_{h}", result)
    return result


def vectorized_backtest(
    price_df: pd.DataFrame,
    signals: dict[str, list[dict]],
    initial_cash: float = 1_000_000.0,
    commission: float = 0.001,
    stamp_duty: float = 0.001,
    slippage: float = 0.001,
    max_positions: int = 20,
) -> dict:
    """Simple vectorized backtester — no event-driven overhead."""

    price_df = price_df.sort_values(["code", "date"]).copy()
    price_df = price_df.set_index(["date", "code"])["close"].unstack()

    dates = sorted(price_df.index)
    cash = initial_cash
    positions: dict[str, float] = {}  # code -> shares
    portfolio_values: list[float] = []

    for dt in dates:
        d_str = str(dt.date())
        prices = price_df.loc[dt].dropna()
        day_signals = signals.get(d_str, [])

        # Process sell signals first
        for sig in day_signals:
            if sig["action"] != "sell":
                continue
            code = sig["code"]
            if code in positions and code in prices.index:
                sell_price = prices[code] * (1 - slippage)
                value = positions[code] * sell_price
                cash += value * (1 - commission - stamp_duty)
                del positions[code]

        # Process buy signals
        for sig in day_signals:
            if sig["action"] != "buy":
                continue
            code = sig["code"]
            if code in positions:
                continue
            if len(positions) >= max_positions:
                continue
            if code not in prices.index:
                continue
            buy_price = prices[code] * (1 + slippage)
            weight = sig.get("weight", 0.05)
            allocation = cash * weight
            shares = int(allocation // buy_price // 100) * 100
            if shares >= 100:
                cost = shares * buy_price
                cash -= cost * (1 + commission)
                positions[code] = shares

        # Mark-to-market portfolio value
        mkt_value = cash
        for code, shares in positions.items():
            if code in prices.index:
                mkt_value += shares * prices[code]
            else:
                mkt_value += shares * prices.get(code, prices.mean())  # fallback
        portfolio_values.append(mkt_value)

    # Compute metrics
    rets = pd.Series(portfolio_values, index=dates).pct_change().dropna()
    total_return = (portfolio_values[-1] / initial_cash - 1) if portfolio_values else 0
    sharpe = float((rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0) - 0.02 / np.sqrt(252)
    # Risk-free adjusted Sharpe
    ann_ret = (1 + total_return) ** (252 / len(rets)) - 1
    ann_vol = float(rets.std() * np.sqrt(252))
    sharpe2 = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0

    peak = pd.Series(portfolio_values).cummax()
    dd = (pd.Series(portfolio_values) - peak) / peak
    max_dd = float(dd.min())

    # Count trades from signals
    n_buys = sum(1 for slist in signals.values() for s in slist if s["action"] == "buy")
    n_sells = sum(1 for slist in signals.values() for s in slist if s["action"] == "sell")

    return {
        "total_return_pct": round(total_return * 100, 2),
        "sharpe_ratio": round(sharpe2, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "total_trades": n_buys + n_sells,
        "win_rate_pct": 0,
        "final_value": round(portfolio_values[-1], 2),
    }


def run_optimized():
    print("=" * 60)
    print("Quant Strategy Verification — Optimized Run")
    print("=" * 60)

    t0 = time.time()

    # Step 1: Data
    print("\n[1/4] Downloading data (parallel)...")
    codes = fetch_index_members("000905")
    print(f"  CSI 500 pool: {len(codes)} stocks")
    sample = codes[:100]
    print(f"  Sample: {len(sample)} stocks")

    df = fetch_all_stocks_parallel(
        sample,
        start=cfg.period.backtest_start,
        end=cfg.period.backtest_end,
    )
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"  Result: {len(df)} rows, {df['code'].nunique()} stocks")
    print(f"  Time: {time.time() - t0:.0f}s")

    # Step 2: Run strategies with vectorized backtester
    print("\n[2/4] Running strategies (vectorized backtester)...")
    results = []

    from strategies.technical.ma_cross import MACrossStrategy
    from strategies.technical.rsi import RSIStrategy
    from strategies.technical.bollinger import BollingerStrategy
    from strategies.technical.macd import MACDStrategy

    for name, cls, stars in [
        ("ma_cross", MACrossStrategy, 10400),
        ("rsi_reversal", RSIStrategy, 10400),
        ("bollinger_breakout", BollingerStrategy, 10400),
        ("macd_signal", MACDStrategy, 10400),
    ]:
        s = cls(pool_name="csi500")
        s.prepare_data(df)
        signals = s.generate_signals()
        sc = sum(len(v) for v in signals.values())
        print(f"  {name:20s} ★ {stars:>6,d} | {sc:>5d} signals", end="")

        r = vectorized_backtest(df, signals)
        r["strategy"] = name
        r["pool"] = "csi500"
        r["source_stars"] = stars
        r["source_project"] = "je-suis-tm/quant-trading"
        r["category"] = "technical"
        results.append(r)
        print(f" → Return: {r['total_return_pct']:>7}%  Sharpe: {r['sharpe_ratio']:>7}  Trades: {r['total_trades']:>5}")

    # Step 3: Summary
    print("\n[3/4] Summary:")
    print(f"  {'Strategy':<20s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s}")
    print("  " + "-" * 55)
    for r in sorted(results, key=lambda x: x.get("sharpe_ratio", -999) or -999, reverse=True):
        print(
            f"  {r['strategy']:<20s} "
            f"{r.get('total_return_pct','N/A'):>8} "
            f"{r.get('sharpe_ratio','N/A'):>8} "
            f"{r.get('max_drawdown_pct','N/A'):>8} "
            f"{r.get('total_trades','N/A'):>8}"
        )

    # Step 4: Report
    print("\n[4/4] Report...")
    generate_markdown_report(results, "final_report.md")
    generate_html_report(results, "final_report.html")
    print("  reports/final_report.md")
    print("  reports/final_report.html")

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print("Done.")


if __name__ == "__main__":
    run_optimized()
