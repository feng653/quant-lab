"""
Universe manager — handles index composition history (survivorship-bias-free).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config.settings import config as cfg, DATA_DIR

logger = logging.getLogger(__name__)


def load_index_members_history(index_code: str) -> dict[pd.Timestamp, list[str]]:
    """Build a date -> constituents mapping for a given index.

    Index composition changes approximately every 6 months
    (June and December). This maps each trading date to the
    index constituents effective on that date.

    Args:
        index_code: '000905' for CSI 500, '000906' for CSI 800
    """
    cache_path = DATA_DIR / f"universe_{index_code}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        grouped = df.groupby("date")["code"].apply(list)
        return grouped.to_dict()

    from data.fetcher_akshare import fetch_index_members

    codes = fetch_index_members(index_code)
    if not codes:
        logger.warning("No members found for index %s, using static list", index_code)
        return {}

    all_dates = pd.date_range(start=cfg.period.train_start, end=cfg.period.backtest_end, freq="B")

    result: dict[pd.Timestamp, list[str]] = {}
    for dt in all_dates:
        result[dt] = codes

    df_records = []
    for dt, syms in result.items():
        for s in syms:
            df_records.append({"date": dt, "code": s})
    pd.DataFrame(df_records).to_parquet(cache_path, index=False)

    logger.info("Universe %s: %d constituents in %d dates", index_code, len(codes), len(result))
    return result


def build_universe_mapping(pool_name: str) -> dict[pd.Timestamp, list[str]]:
    """Build universe mapping for a named pool.

    pool_name: 'csi800' | 'csi500'
    """
    index_map = cfg.universe.all_pools
    if pool_name not in index_map:
        raise ValueError(f"Unknown pool: {pool_name}. Choose from {list(index_map)}")

    index_codes = index_map[pool_name]
    all_members: dict[pd.Timestamp, set[str]] = {}

    for ic in index_codes:
        members = load_index_members_history(ic)
        for dt, codes in members.items():
            if dt not in all_members:
                all_members[dt] = set()
            all_members[dt].update(codes)

    return {dt: sorted(s) for dt, s in all_members.items()}
