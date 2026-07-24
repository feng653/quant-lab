"""Sequential test — avoids mini_racer threading crash, uses 100 stocks."""

import sys

sys.path.insert(0, ".")

import logging

logging.basicConfig(level=logging.WARNING)

import time

import numpy as np
import pandas as pd

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members, _cache_path, _save_cache
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


def _fetch_one_baostock(sym: str, start: str, end: str) -> pd.DataFrame | None:
    import baostock as bs

    try:
        bs.login()
        prefix = "sh" if sym.startswith("6") else "sz"
        rs = bs.query_history_k_data_plus(
            f"{prefix}.{sym}",
            "date,open,high,low,close,volume,amount,turn",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            frequency="d",
            adjustflag="2",
        )
        items = []
        while rs.next():
            items.append(rs.get_row_data())
        bs.logout()
        if not items:
            return None
        df = pd.DataFrame(items, columns=["date", "open", "high", "low", "close", "volume", "amount", "turnover"])
        for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["code"] = sym
        return df
    except Exception:
        return None


def vectorized_backtest(
    price_df: pd.DataFrame,
    signals: dict[str, list[dict]],
    initial_cash: float = 1_000_000.0,
    commission: float = 0.001,
    stamp_duty: float = 0.001,
    slippage: float = 0.001,
    max_positions: int = 20,
) -> dict:
    price_df = price_df.sort_values(["code", "date"]).copy()
    price_df = price_df.set_index(["date", "code"])["close"].unstack()
    dates = sorted(price_df.index)
    cash = initial_cash
    positions: dict[str, float] = {}
    portfolio_values: list[float] = []

    for dt in dates:
        d_str = str(dt.date())
        prices = price_df.loc[dt].dropna()
        day_signals = signals.get(d_str, [])

        for sig in day_signals:
            if sig["action"] != "sell":
                continue
            code = sig["code"]
            if code in positions and code in prices.index:
                sp = prices[code] * (1 - slippage)
                cash += positions[code] * sp * (1 - commission - stamp_duty)
                del positions[code]

        for sig in day_signals:
            if sig["action"] != "buy":
                continue
            code = sig["code"]
            if code in positions or len(positions) >= max_positions:
                continue
            if code not in prices.index:
                continue
            bp = prices[code] * (1 + slippage)
            w = sig.get("weight", 0.05)
            shares = int(cash * w // bp // 100) * 100
            if shares >= 100:
                cash -= shares * bp * (1 + commission)
                positions[code] = shares

        mkt = cash + sum(
            positions[c] * (prices[c] if c in prices.index else 0) for c in positions
        )
        portfolio_values.append(mkt)

    rets = pd.Series(portfolio_values, index=dates).pct_change().dropna()
    tr = (portfolio_values[-1] / initial_cash - 1) if portfolio_values else 0
    ann_ret = (1 + tr) ** (252 / max(len(rets), 1)) - 1
    ann_vol = float(rets.std() * np.sqrt(252))
    sharpe = (ann_ret - 0.02) / ann_vol if ann_vol > 0 else 0
    peak = pd.Series(portfolio_values).cummax()
    mdd = float((pd.Series(portfolio_values) - peak).div(peak).min())

    n_buys = sum(1 for sl in signals.values() for s in sl if s["action"] == "buy")
    n_sells = sum(1 for sl in signals.values() for s in sl if s["action"] == "sell")

    return {
        "total_return_pct": round(tr * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(mdd * 100, 2),
        "total_trades": n_buys + n_sells,
        "win_rate_pct": 0,
        "final_value": round(portfolio_values[-1], 2),
    }


def main():
    print("=" * 60)
    print("Quant Strategy Verification — Sequential Run")
    print("=" * 60)
    t0 = time.time()

    print("\n[1/4] Downloading data...")
    codes = fetch_index_members("000905")
    print(f"  CSI 500 pool: {len(codes)} stocks")
    sample = codes[:80]
    print(f"  Sample: {len(sample)} stocks (sequential download)")

    frames = []
    for i, sym in enumerate(sample):
        if (i + 1) % 20 == 0:
            print(f"    {i + 1}/{len(sample)}...")
        r = _fetch_one_akshare(sym, cfg.period.backtest_start, cfg.period.backtest_end)
        if r is not None:
            frames.append(r)

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"  Data: {len(df)} rows, {df['code'].nunique()} stocks ({time.time() - t0:.0f}s)")

    print("\n[2/4] Running strategies...")
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
        st = time.time()
        s = cls(pool_name="csi500")
        s.prepare_data(df)
        signals = s.generate_signals()
        sc = sum(len(v) for v in signals.values())

        r = vectorized_backtest(df, signals)
        r["strategy"] = name
        r["pool"] = "csi500"
        r["source_stars"] = stars
        r["source_project"] = "je-suis-tm/quant-trading"
        r["category"] = "technical"
        results.append(r)
        print(f"  {name:20s} ★ {stars:>6,d} | {sc:>5d} sigs | {time.time()-st:.0f}s → Ret:{r['total_return_pct']:>7}%  Shp:{r['sharpe_ratio']:>6}  DD:{r['max_drawdown_pct']:>6}%")

    print("\n[3/4] Summary:")
    print(f"  {'Strategy':<20s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s}")
    print("  " + "-" * 55)
    for r in sorted(results, key=lambda x: x.get("sharpe_ratio", -999) or -999, reverse=True):
        print(f"  {r['strategy']:<20s} {r['total_return_pct']:>8} {r['sharpe_ratio']:>8} {r['max_drawdown_pct']:>8} {r['total_trades']:>8}")

    print("\n[4/4] Report...")
    generate_markdown_report(results, "final_report.md")
    generate_html_report(results, "final_report.html")
    print(f"  Done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
