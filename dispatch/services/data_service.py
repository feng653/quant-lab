"""
Unified data service — single entry point for pool OHLCV data and benchmark index.

- load_pool(): read the full-history cache parquet for a pool
- auto_update(): incrementally fetch missing trading days and append to cache
- load_benchmark(): CSI 500 index daily closes (cached, auto-updated)

All dispatch scripts must use this module instead of touching cache files directly.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "core" / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BENCH_SYMBOL = "000905"  # CSI 500
_CAL_CACHE: dict[str, list[str]] = {}


# ────────────────────────── trading calendar ──────────────────────────

def trading_days(start: str, end: str) -> list[str]:
    """Trading days in [start, end] as YYYY-MM-DD strings (sina calendar, cached)."""
    key = f"{start}_{end}"
    if key not in _CAL_CACHE:
        try:
            import akshare as ak
            cal = ak.tool_trade_date_hist_sina()
            days = [str(d) for d in cal["trade_date"]]
        except Exception as e:
            logger.warning("Calendar fetch failed, fallback to weekdays: %s", e)
            days = [(datetime.strptime(start, "%Y-%m-%d") + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range((datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 1)]
            days = [d for d in days if datetime.strptime(d, "%Y-%m-%d").weekday() < 5]
        _CAL_CACHE[key] = [d for d in days if start <= d <= end]
    return _CAL_CACHE[key]


def is_trading_day(date_str: str | None = None) -> bool:
    d = date_str or datetime.now().strftime("%Y-%m-%d")
    return d in trading_days(d, d)


def latest_completed_trading_day() -> str:
    """Latest trading day whose close data should be available.

    Before 15:00 on a trading day the bar is incomplete → use previous trading day.
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    start = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    days = trading_days(start, today)
    if not days:
        return today
    if days[-1] == today and now.hour < 15:
        return days[-2] if len(days) >= 2 else days[-1]
    return days[-1]


# ────────────────────────── pool data ──────────────────────────

def pool_file(pool: str) -> Path | None:
    """Locate the full-history cache file for a pool."""
    files = sorted(CACHE_DIR.glob(f"full_{pool}_*.parquet"), key=lambda f: f.stat().st_mtime)
    return files[-1] if files else None


def load_pool(pool: str = "csi500") -> pd.DataFrame:
    f = pool_file(pool)
    if f is None:
        logger.error("No cache file for pool %s", pool)
        return pd.DataFrame()
    df = pd.read_parquet(f)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _fetch_one_stock(code: str, start: str, end: str, retries: int = 2) -> pd.DataFrame:
    import akshare as ak
    prefix = "sh" if code.startswith("6") else "sz"
    for attempt in range(retries + 1):
        try:
            # NOTE: qfq prices anchor to the latest trading day; rows may shift slightly
            # for stocks with corporate actions inside the gap window. Accepted tradeoff.
            r = ak.stock_zh_a_daily(symbol=f"{prefix}{code}",
                                    start_date=start.replace("-", ""),
                                    end_date=end.replace("-", ""), adjust="qfq")
            if r is not None and not r.empty:
                r["code"] = code
                return r
            return pd.DataFrame()
        except Exception:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return pd.DataFrame()


def auto_update(pool: str = "csi500") -> tuple[pd.DataFrame, str, int]:
    """Append missing trading days to the pool cache.

    Returns (df, latest_date_str, n_days_added).
    """
    df = load_pool(pool)
    if df.empty:
        return df, "", 0

    last = df["date"].max().strftime("%Y-%m-%d")
    target = latest_completed_trading_day()
    if target <= last:
        return df, last, 0

    missing = trading_days(last, target)
    missing = [d for d in missing if d > last]
    if not missing:
        return df, last, 0

    codes = sorted(df["code"].unique())
    logger.info("Updating %s: %s → %s (%d days, %d stocks)", pool, last, target, len(missing), len(codes))

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_fetch_one_stock, c, missing[0], missing[-1]): c for c in codes}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            if not r.empty:
                frames.append(r)
            done += 1
            if done % 100 == 0:
                logger.info("  fetched %d/%d stocks", done, len(codes))
            time.sleep(0.02)

    if not frames:
        logger.warning("No new data fetched")
        return df, last, 0

    new = pd.concat(frames, ignore_index=True)
    new["date"] = pd.to_datetime(new["date"])
    keep = [c for c in df.columns if c in new.columns]
    new = new[keep]

    combined = pd.concat([df, new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "code"], keep="last").sort_values(["date", "code"])

    f = pool_file(pool)
    combined.to_parquet(f, index=False)
    latest = combined["date"].max().strftime("%Y-%m-%d")
    added_days = combined["date"].nunique() - df["date"].nunique()
    logger.info("Cache updated → %s (+%d days, %d rows)", latest, added_days, len(new))
    return combined, latest, added_days


# ────────────────────────── benchmark index ──────────────────────────

def _bench_file() -> Path:
    return CACHE_DIR / f"index_{BENCH_SYMBOL}.parquet"


def load_benchmark(start: str | None = None, end: str | None = None) -> pd.Series:
    """CSI 500 daily close series, cached and auto-updated."""
    f = _bench_file()
    df = pd.read_parquet(f) if f.exists() else pd.DataFrame()

    target = latest_completed_trading_day()
    need_from = start or "2024-01-01"
    stale = df.empty or pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d") < target

    if stale:
        try:
            import akshare as ak
            new = pd.DataFrame()
            try:
                r = ak.stock_zh_index_daily(symbol=f"sh{BENCH_SYMBOL}")  # sina, full history
                if r is not None and not r.empty:
                    new = pd.DataFrame({"date": pd.to_datetime(r["date"]), "close": r["close"].astype(float)})
            except Exception:
                r = ak.index_zh_a_hist(symbol=BENCH_SYMBOL, period="daily",
                                       start_date=need_from.replace("-", ""),
                                       end_date=target.replace("-", ""))
                if r is not None and not r.empty:
                    new = pd.DataFrame({"date": pd.to_datetime(r["日期"]), "close": r["收盘"].astype(float)})
            if not new.empty:
                df = pd.concat([df, new], ignore_index=True).drop_duplicates(subset=["date"], keep="last")
                df = df.sort_values("date")
                df.to_parquet(f, index=False)
        except Exception as e:
            logger.warning("Benchmark update failed: %s", e)

    if df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(df["close"].values, index=pd.to_datetime(df["date"]))
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    if end:
        s = s[s.index <= pd.Timestamp(end)]
    return s
