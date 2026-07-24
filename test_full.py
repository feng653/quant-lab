"""Full-scale test — CSI 500 stocks, 4 technical strategies, 2024-2026."""

import sys

sys.path.insert(0, ".")

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members, fetch_daily_kline
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from strategies.technical.ma_cross import MACrossStrategy
from strategies.technical.rsi import RSIStrategy
from strategies.technical.bollinger import BollingerStrategy
from strategies.technical.macd import MACDStrategy
from strategies.portfolio.pairs_trading import PairsTradingStrategy
from backtest.engine import run_single_strategy
from evaluation.report import generate_markdown_report, generate_html_report


def run_full():
    print("=" * 60)
    print("Full Strategy Verification — CSI 500 | 2024-2026")
    print("=" * 60)

    print("\n[1/4] Downloading CSI 500 data...")
    codes = fetch_index_members("000905")
    print(f"  Pool: {len(codes)} stocks")

    test_codes = codes  # all CSI 500 stocks
    print(f"  Testing: {len(test_codes)} stocks (full CSI 500)")
    print(f"  Period: {cfg.period.backtest_start} ~ {cfg.period.backtest_end}")

    df = fetch_daily_kline(
        test_codes,
        start=cfg.period.backtest_start,
        end=cfg.period.backtest_end,
        adjust="qfq",
    )
    df = clean_ohlcv(df)
    df = compute_returns(df)
    df = price_limit_filter(df)
    print(f"  Data: {len(df)} rows, {df['code'].nunique()} stocks")
    print(f"  Range: {df['date'].min().date()} ~ {df['date'].max().date()}")

    print("\n[2/4] Running strategies...")
    results = []

    strategies = [
        ("ma_cross", MACrossStrategy, 10400),
        ("rsi_reversal", RSIStrategy, 10400),
        ("bollinger_breakout", BollingerStrategy, 10400),
        ("macd_signal", MACDStrategy, 10400),
    ]

    for name, cls, stars in strategies:
        s = cls(pool_name="csi500")
        s.prepare_data(df)
        signals = s.generate_signals()
        sc = sum(len(v) for v in signals.values())
        print(f"  {name:20s} ★ {stars:>6,d} | {sc:>5d} signals → backtesting...", end=" ")

        result = run_single_strategy(df, signals, "csi500", name)
        result["source_stars"] = stars
        result["source_project"] = "je-suis-tm/quant-trading"
        result["category"] = "technical"
        results.append(result)
        print(f"Return: {result.get('total_return_pct','?'):>6}%  Sharpe: {result.get('sharpe_ratio','?'):>6}  Trades: {result.get('total_trades','?'):>4}")

    print("\n[3/4] Summary:")
    print(f"  {'Strategy':<20s} {'Return%':>8s} {'Sharpe':>8s} {'MaxDD%':>8s} {'Trades':>8s} {'WinRate%':>10s}")
    print("  " + "-" * 62)
    for r in sorted(results, key=lambda x: x.get("sharpe_ratio", -999) or -999, reverse=True):
        print(
            f"  {r['strategy']:<20s} "
            f"{r.get('total_return_pct','N/A'):>8} "
            f"{r.get('sharpe_ratio','N/A'):>8} "
            f"{r.get('max_drawdown_pct','N/A'):>8} "
            f"{r.get('total_trades','N/A'):>8} "
            f"{r.get('win_rate_pct','N/A'):>10}"
        )

    print("\n[4/4] Generating report...")
    generate_markdown_report(results, "full_report.md")
    generate_html_report(results, "full_report.html")
    print("  Done: reports/full_report.md, reports/full_report.html")

    print("\n" + "=" * 60)
    print("Full test complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_full()
