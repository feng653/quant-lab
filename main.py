"""
Entry point — Multi-strategy quantitative verification pipeline for Chinese A-shares.

Usage:
    # Download data and prepare universe
    python main.py --step data --pool csi800

    # Run all technical strategies
    python main.py --step backtest --strategies ma_cross,rsi_reversal,bollinger_breakout,macd_signal

    # Run ML strategies (via Qlib)
    python main.py --step ml --strategies alpha158_lgb,alpha158_xgb,lstm_rank

    # Run everything and generate comparison report
    python main.py --step all --pool csi800,csi500 --device cuda
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import config as cfg
from data.akshare_fetcher import fetch_daily_kline, fetch_index_members
from data.processor import clean_ohlcv, compute_returns, price_limit_filter
from data.universe import build_universe_mapping
from strategies.stars_tags import STRATEGY_CATALOG, STRATEGY_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def step_data(pools: list[str]) -> pd.DataFrame:
    """Download and prepare data for all specified pools."""
    logger.info("=== Step 1: Downloading data ===")
    codes: list[str] = []
    for pool in pools:
        idx = cfg.universe.all_pools[pool][0]
        members = fetch_index_members(idx)
        codes.extend(members)
    codes = sorted(set(codes))
    logger.info("Total unique stocks: %d", len(codes))

    df = fetch_daily_kline(
        codes,
        start=cfg.period.train_start,
        end=cfg.period.backtest_end,
    )
    df = clean_ohlcv(df)
    df = price_limit_filter(df)
    df = compute_returns(df)
    logger.info("Data ready: %d rows, %d stocks, %s - %s", len(df), df["code"].nunique(), df["date"].min().date(), df["date"].max().date())
    return df


def step_backtest(price_df: pd.DataFrame, pools: list[str], strategy_names: list[str]) -> list[dict]:
    """Run backtest for the specified strategies and pools."""
    logger.info("=== Step 2: Running backtests ===")
    from backtest.runner import run_all
    results = run_all(price_df, pools, strategy_names)
    return results


def step_ml(price_df: pd.DataFrame, pools: list[str], strategies: list[str], device: str) -> list[dict]:
    """Run ML strategies via Qlib."""
    logger.info("=== Step 3: Running ML strategies (device=%s) ===", device)
    results: list[dict] = []

    for pool in pools:
        if "alpha158_lgb" in strategies:
            logger.info("  alpha158_lgb [Qlib ★ 46.6k] pool=%s", pool)
            from strategies.factor.alpha158 import Alpha158LGBStrategy
            s = Alpha158LGBStrategy(pool_name=pool)
            s.prepare_data(price_df)
            signals = s.generate_signals()
            from backtest.engine import run_single_strategy
            r = run_single_strategy(price_df, signals, pool, "alpha158_lgb")
            r.update({"source_stars": 46600, "source_project": "microsoft/qlib", "category": "factor"})
            results.append(r)

        if "alpha158_xgb" in strategies:
            logger.info("  alpha158_xgb [Qlib ★ 46.6k] pool=%s", pool)
            from strategies.factor.alpha360 import Alpha158XGBStrategy
            s = Alpha158XGBStrategy(pool_name=pool)
            s.prepare_data(price_df)
            signals = s.generate_signals()
            from backtest.engine import run_single_strategy
            r = run_single_strategy(price_df, signals, pool, "alpha158_xgb")
            r.update({"source_stars": 46600, "source_project": "microsoft/qlib", "category": "factor"})
            results.append(r)

        if "lstm_rank" in strategies:
            logger.info("  lstm_rank [Qlib ★ 46.6k] pool=%s device=%s", pool, device)
            from strategies.ml.lstm_transformer import LSTMStrategy
            s = LSTMStrategy(pool_name=pool, device=device)
            s.prepare_data(price_df)
            signals = s.generate_signals()
            from backtest.engine import run_single_strategy
            r = run_single_strategy(price_df, signals, pool, "lstm_rank")
            r.update({"source_stars": 46600, "source_project": "microsoft/qlib", "category": "ml"})
            results.append(r)

    return results


def step_report(results: list[dict]) -> None:
    """Generate comparison reports."""
    logger.info("=== Step 4: Generating reports ===")
    from evaluation.comparison import run_comparison
    files = run_comparison(results)
    for fmt, path in files.items():
        logger.info("  Report (%s): %s", fmt, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-strategy quantitative verification pipeline")
    parser.add_argument("--step", default="all", choices=["data", "backtest", "ml", "report", "all"])
    parser.add_argument("--pool", default="csi800,csi500", help="Comma-separated: csi800,csi500")
    parser.add_argument("--strategies", default="ma_cross,rsi_reversal,bollinger_breakout,macd_signal", help="Comma-separated strategy names")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--list-strategies", action="store_true", help="List all available strategies")
    args = parser.parse_args()

    if args.list_strategies:
        print("\nAvailable strategies:\n")
        for m in sorted(STRATEGY_CATALOG, key=lambda x: x.source_stars, reverse=True):
            print(f"  {m.name:25s} ★ {m.source_stars:>6,d}  [{m.category:>10}] {m.description}")
        return

    pools = args.pool.split(",")
    strategies = args.strategies.split(",")

    results: list[dict] = []

    if args.step in ("data", "all"):
        price_df = step_data(pools)
    else:
        price_df = pd.DataFrame()

    if args.step in ("backtest", "all"):
        results.extend(step_backtest(price_df, pools, strategies))

    if args.step in ("ml", "all"):
        results.extend(step_ml(price_df, pools, strategies, args.device))

    if args.step in ("report", "all"):
        step_report(results)

    if results:
        logger.info("Done. %d strategy-pool combinations evaluated.", len(results))
        if args.step != "report":
            step_report(results)


if __name__ == "__main__":
    main()
