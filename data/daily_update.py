"""
Daily data update — incrementally downloads latest trading day's data.

Usage: python data/daily_update.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import sys

sys.path.insert(0, str(__path__[0] + "/..") if __path__ else "..")

import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from config.settings import config as cfg
from data.akshare_fetcher import fetch_index_members

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)

INDEX_CACHE_FILE = CACHE / "index_members.parquet"
OHLCV_CACHE_FILE = CACHE / "daily_ohlcv.parquet"


def is_trading_day(date_str: str) -> bool:
    """Check if date is a trading day (Mon-Fri, not a CNY holiday)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:
        return False
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        cal_dates = set(cal["trade_date"].astype(str))
        return date_str in cal_dates or date_str.replace("-", "") in cal_dates
    except Exception:
        return dt.weekday() < 5


def refresh_index_members() -> dict[str, list[str]]:
    """Refresh index constituents for all configured pools."""
    members: dict[str, list[str]] = {}
    for pool_name, idx_codes in cfg.universe.all_pools.items():
        all_codes: list[str] = []
        for ic in idx_codes:
            try:
                all_codes.extend(fetch_index_members(ic))
            except Exception as e:
                logger.warning("Failed to fetch %s members: %s", ic, e)
        members[pool_name] = sorted(set(all_codes))
        logger.info("Pool %s: %d constituents", pool_name, len(members[pool_name]))

    df = pd.DataFrame([{"pool": k, "codes": v, "updated": pd.Timestamp.now().isoformat()} for k, v in members.items()])
    df.to_parquet(INDEX_CACHE_FILE, index=False)
    return members


def update_daily_data(date_str: str | None = None) -> pd.DataFrame:
    """Download the latest trading day's data and append to cache."""
    if date_str is None:
        today = datetime.now()
        if today.hour < 16:
            today -= timedelta(days=1)
        date_str = today.strftime("%Y-%m-%d")

    if not is_trading_day(date_str):
        logger.info("%s is not a trading day, skipping", date_str)
        return pd.DataFrame()

    # Load existing cache
    existing = pd.DataFrame()
    if OHLCV_CACHE_FILE.exists():
        existing = pd.read_parquet(OHLCV_CACHE_FILE)

    # Check if date already cached
    if not existing.empty:
        existing_dates = pd.to_datetime(existing["date"]).dt.strftime("%Y-%m-%d")
        if date_str in existing_dates.values:
            logger.info("%s already cached, skipping", date_str)
            return existing

    # Get all tracked stocks
    all_codes: list[str] = []
    if not existing.empty:
        all_codes = existing["code"].unique().tolist()
    else:
        for ic in cfg.universe.all_pools.get("csi500", ["000905"]):
            all_codes.extend(fetch_index_members(ic))
    all_codes = sorted(set(all_codes))

    # Fetch latest day
    import akshare as ak

    frames: list[pd.DataFrame] = []
    for sym in all_codes[:200]:  # limit to avoid overload
        try:
            prefix = "sh" if sym.startswith("6") else "sz"
            df = ak.stock_zh_a_daily(symbol=f"{prefix}{sym}", start_date=date_str.replace("-", ""), end_date=date_str.replace("-", ""), adjust="qfq")
            if not df.empty:
                df["code"] = sym
                frames.append(df)
        except Exception:
            logger.debug("Skip %s: download failed", sym)

    if not frames:
        logger.warning("No data for %s", date_str)
        return existing

    new_data = pd.concat(frames, ignore_index=True)
    new_data["date"] = pd.to_datetime(new_data["date"])
    logger.info("Downloaded %d rows for %s (%d stocks)", len(new_data), date_str, new_data["code"].nunique())

    # Append to cache
    if not existing.empty:
        combined = pd.concat([existing, new_data], ignore_index=True).drop_duplicates(subset=["date", "code"])
    else:
        combined = new_data

    combined.to_parquet(OHLCV_CACHE_FILE, index=False)
    return combined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Date to update (YYYY-MM-DD)")
    parser.add_argument("--refresh-index", action="store_true", help="Refresh index members")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.refresh_index:
        members = refresh_index_members()
        print(f"Refreshed index members: { {k: len(v) for k, v in members.items()} }")

    result = update_daily_data(args.date)
    if not result.empty:
        latest_date = pd.to_datetime(result["date"]).max().strftime("%Y-%m-%d")
        print(f"Data updated through {latest_date}, {len(result)} total rows")


if __name__ == "__main__":
    main()
