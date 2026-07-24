"""
Batch runner — orchestrates multiple strategies across multiple stock pools.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from config.settings import config as cfg
from backtest.engine import run_single_strategy
from strategies.stars_tags import STRATEGY_CATALOG, STRATEGY_MAP

logger = logging.getLogger(__name__)


def run_all(
    price_df: pd.DataFrame,
    pools: list[str] | None = None,
    strategy_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run all strategies across all pools.

    Args:
        price_df: Cleaned OHLCV data with columns [date, code, open, high, low, close, volume]
        pools: ['csi800', 'csi500'], defaults to all configured pools
        strategy_names: list of strategy names to run, defaults to all catalogued

    Returns:
        List of result dicts, one per (strategy, pool) combination.
    """
    if pools is None:
        pools = list(cfg.universe.all_pools)
    if strategy_names is None:
        strategy_names = [m.name for m in STRATEGY_CATALOG]

    from strategies.technical.ma_cross import MACrossStrategy
    from strategies.technical.rsi import RSIStrategy
    from strategies.technical.bollinger import BollingerStrategy
    from strategies.technical.macd import MACDStrategy

    strategy_classes: dict[str, type] = {
        "ma_cross": MACrossStrategy,
        "rsi_reversal": RSIStrategy,
        "bollinger_breakout": BollingerStrategy,
        "macd_signal": MACDStrategy,
    }

    results: list[dict[str, Any]] = []

    for pool_name in pools:
        pool_price = price_df.copy()
        logger.info("Running pool=%s (%d stocks)", pool_name, pool_price["code"].nunique())

        for sname in strategy_names:
            meta = STRATEGY_MAP.get(sname)
            if meta is None:
                logger.warning("Unknown strategy: %s, skipping", sname)
                continue

            cls = strategy_classes.get(sname)
            if cls is None:
                logger.info("Strategy %s not implemented via direct class (uses Qlib or other backend)", sname)
                continue

            logger.info("  [%s] ★ %d | %s", sname, meta.source_stars, meta.description)
            strategy = cls(pool_name=pool_name)
            strategy.prepare_data(pool_price)
            signals = strategy.generate_signals()
            result = run_single_strategy(pool_price, signals, pool_name, sname)
            result["source_stars"] = meta.source_stars
            result["source_project"] = meta.source_project
            result["category"] = meta.category
            results.append(result)

    return results
