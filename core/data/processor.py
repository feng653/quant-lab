"""
Data processor — cleaning, alignment, and preparation for backtesting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate OHLCV data.

    - Drop rows with NaN in key columns
    - Remove zero-volume rows (suspended stocks)
    - Sort by date
    """
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[df["volume"] > 0].copy()
    df = df.sort_values("date")
    return df


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily returns for each stock."""
    df = df.sort_values(["code", "date"])
    df["ret"] = df.groupby("code")["close"].pct_change()
    return df


def price_limit_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Mark stocks at daily price limits (A-share: ±10%, STAR: ±20%).

    These stocks are illiquid at the limit and should be
    excluded from trading signals on that day.
    """
    df = df.copy()
    df["limit_up"] = df.groupby("code")["close"].transform(
        lambda x: x.pct_change() >= 0.098
    )
    df["limit_down"] = df.groupby("code")["close"].transform(
        lambda x: x.pct_change() <= -0.098
    )
    return df


def align_universe(
    price_df: pd.DataFrame,
    members_by_date: dict[pd.Timestamp, list[str]],
) -> pd.DataFrame:
    """Filter price data to only include stocks that are index constituents on each date.

    Handles index composition changes (调入/调出) to avoid survivorship bias.
    """
    if not members_by_date:
        return price_df

    frames: list[pd.DataFrame] = []
    for dt, codes in members_by_date.items():
        day_data = price_df[price_df["date"] == dt]
        day_data = day_data[day_data["code"].isin(codes)]
        frames.append(day_data)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["date", "code"])
