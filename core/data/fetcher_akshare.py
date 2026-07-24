"""
AKShare data fetcher — primary data source for Chinese A-share markets.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from config.settings import config as cfg, DATA_DIR

logger = logging.getLogger(__name__)


def _cache_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(name.encode()).hexdigest()[:12]
    return DATA_DIR / f"{h}.parquet"


def _load_cache(name: str) -> pd.DataFrame | None:
    p = _cache_path(name)
    if p.exists():
        return pd.read_parquet(p)
    return None


def _save_cache(name: str, df: pd.DataFrame) -> None:
    df.to_parquet(_cache_path(name), index=False)


def fetch_index_members(index_code: str, date_str: str | None = None) -> list[str]:
    """Fetch CSI 500 or CSI 800 constituent stocks via AKShare.

    Source: stock_board_concept_hist_em or index_stock_cons
    Stars: ★ 21.5k (akshare)
    """
    cache_key = f"members_{index_code}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached["code"].unique().tolist()

    import akshare as ak

    df = ak.index_stock_cons(symbol=index_code)
    df = df[["品种代码"]].rename(columns={"品种代码": "code"}).drop_duplicates()
    _save_cache(cache_key, df)
    logger.info("AKShare: fetched %d constituents for %s", len(df), index_code)
    return df["code"].unique().tolist()


def fetch_daily_kline(
    symbols: list[str],
    start: str = "2019-01-01",
    end: str = "2026-06-30",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """Fetch daily OHLCV for a list of A-share stocks via AKShare.

    adjust: 'qfq' = 前复权, 'hfq' = 后复权
    Stars: ★ 21.5k (akshare)
    """
    cache_key = f"daily_{'_'.join(sorted(symbols))}_{start}_{end}_{adjust}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    import akshare as ak

    frames: list[pd.DataFrame] = []
    for sym in symbols:
        try:
            prefix = "sh" if sym.startswith("6") else "sz"
            ak_sym = f"{prefix}{sym}"
            df = ak.stock_zh_a_daily(
                symbol=ak_sym,
                start_date=start.replace("-", ""),
                end_date=end.replace("-", ""),
                adjust=adjust,
            )
            df["code"] = sym
            frames.append(df)
        except Exception:
            logger.debug("AKShare: skip %s (no data)", sym)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])
    _save_cache(cache_key, result)
    logger.info("AKShare: fetched daily data for %d symbols, %d rows", len(symbols), len(result))
    return result


def fetch_financials(symbols: list[str]) -> pd.DataFrame:
    """Fetch financial statement indicators for A-share stocks.

    Includes PE, PB, ROE, revenue growth, profit margin, etc.
    Stars: ★ 21.5k (akshare)
    """
    cache_key = f"fin_{'_'.join(sorted(symbols))}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    import akshare as ak

    frames: list[pd.DataFrame] = []
    for sym in symbols:
        try:
            df = ak.stock_financial_abstract(symbol=sym)
            df["code"] = sym
            frames.append(df)
        except Exception:
            logger.debug("AKShare: skip financials for %s", sym)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    _save_cache(cache_key, result)
    logger.info("AKShare: fetched financials for %d symbols", len(symbols))
    return result
