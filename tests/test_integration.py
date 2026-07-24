"""Quick integration test — validates the pipeline end-to-end."""

import sys

sys.path.insert(0, ".")

from config.settings import config as cfg
from data.fetcher_akshare import fetch_index_members, fetch_daily_kline
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from strategies.technical.ma_cross import MACrossStrategy
from strategies.technical.rsi import RSIStrategy
from strategies.technical.bollinger import BollingerStrategy
from strategies.technical.macd import MACDStrategy
from backtest.engine import run_single_strategy
from backtest.runner import run_all


def main():
    print("=" * 60)
    print("Quant Strategy Verification — Integration Test")
    print("=" * 60)

    # Step 1: Small data sample
    print("\n[1/4] Downloading test data...")
    codes = fetch_index_members("000905")[:10]
    print(f"  Test symbols: {codes}")

    df = fetch_daily_kline(codes, start="2024-01-01", end="2025-12-31", adjust="qfq")
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"  Data: {len(df)} rows, {df['code'].nunique()} stocks")
    print(f"  Range: {df['date'].min().date()} ~ {df['date'].max().date()}")

    # Step 2: Test each technical strategy
    print("\n[2/4] Testing technical strategies...")
    strategies = [
        ("ma_cross", MACrossStrategy),
        ("rsi_reversal", RSIStrategy),
        ("bollinger_breakout", BollingerStrategy),
        ("macd_signal", MACDStrategy),
    ]

    results = []
    for name, cls in strategies:
        s = cls(pool_name="csi500")
        s.prepare_data(df)
        signals = s.generate_signals()
        signal_count = sum(len(v) for v in signals.values())
        print(f"  {name:20s} → {signal_count:4d} signals")

        result = run_single_strategy(df, signals, "csi500", name)
        result["source_stars"] = s.meta.source_stars
        result["source_project"] = s.meta.source_project
        result["category"] = s.meta.category
        results.append(result)

    # Step 3: Show results
    print("\n[3/4] Backtest results:")
    print(f"  {'Strategy':<20s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s}")
    print("  " + "-" * 55)
    for r in sorted(results, key=lambda x: x.get("sharpe_ratio", 0) or 0, reverse=True):
        print(
            f"  {r['strategy']:<20s} "
            f"{r.get('total_return_pct','N/A'):>8} "
            f"{r.get('sharpe_ratio','N/A'):>8} "
            f"{r.get('max_drawdown_pct','N/A'):>8} "
            f"{r.get('total_trades','N/A'):>8}"
        )

    # Step 4: Generate report
    print("\n[4/4] Generating report...")
    from evaluation.report import generate_markdown_report, generate_html_report

    for r in results:
        r["source_stars"] = r.get("source_stars", 0)
        r["source_project"] = r.get("source_project", "")
        r["category"] = r.get("category", "")

    md = generate_markdown_report(results, "test_report.md")
    html = generate_html_report(results, "test_report.html")
    print(f"  Reports generated: reports/test_report.md, reports/test_report.html")

    print("\n" + "=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
