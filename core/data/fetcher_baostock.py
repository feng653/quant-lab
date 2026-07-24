"""
BaoStock data fetcher — fallback data source for core OHLCV and financials.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pandas as pd

from config.settings import config as cfg, DATA_DIR

logger = logging.getLogger(__name__)


def _cache_path(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(name.encode()).hexdigest()[:12]
    return DATA_DIR / f"bs_{h}.parquet"


def _load_cache(name: str) -> pd.DataFrame | None:
    p = _cache_path(name)
    if p.exists():
        return pd.read_parquet(p)
    return None


def _save_cache(name: str, df: pd.DataFrame) -> None:
    df.to_parquet(_cache_path(name), index=False)


def fetch_daily_kline_bs(
    symbols: list[str],
    start: str = "2019-01-01",
    end: str = "2026-06-30",
) -> pd.DataFrame:
    """Fetch daily OHLCV from BaoStock as fallback.

    BaoStock runs its own dedicated data server (not web scraping),
    making it more stable for core historical data.
    Stars: community (baostock)
    """
    cache_key = f"daily_{'_'.join(sorted(symbols))}_{start}_{end}"
    cached = _load_cache(cache_key)
    if cached is not None:
        return cached

    import baostock as bs

    lg = bs.login()
    if lg.error_code != "0":
        logger.error("BaoStock login failed: %s", lg.error_msg)
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for sym in symbols:
        bs_code = f"sh.{sym}" if sym.startswith("6") else f"sz.{sym}"
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount,turn,pctChg",
            start_date=start.replace("-", ""),
            end_date=end.replace("-", ""),
            frequency="d",
            adjustflag="2",  # 前复权
        )
        items: list[dict] = []
        while rs.next():
            items.append(rs.get_row_data())
        if items:
            df = pd.DataFrame(items, columns=["date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"])
            for col in ["open", "high", "low", "close", "volume", "amount", "turnover"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["code"] = sym
            frames.append(df)

    bs.logout()

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result["date"] = pd.to_datetime(result["date"])
    _save_cache(cache_key, result)
    logger.info("BaoStock: fetched daily data for %d symbols", len(symbols))
    return result
