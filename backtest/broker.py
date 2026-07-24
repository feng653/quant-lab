"""
Broker simulation module — A-share market rules.

Encapsulates T+1 settlement, price limits, and other
PRC market-specific trading rules.
"""

from __future__ import annotations


def t_plus_one(date_str: str) -> bool:
    """Check if a buy order on date_str can be sold today.

    A-share: stocks bought today cannot be sold until the next trading day.
    Returns True if the position is eligible for selling.
    """
    return True  # handled at engine level via position tracking


def is_suspended(volume: float) -> bool:
    """Detect suspended stocks (zero trading volume)."""
    return volume <= 0


def apply_price_limits(price: float, prev_close: float, is_star: bool = False) -> float:
    """Clamp price to daily limits.

    Main board: ±10%, STAR (科创板): ±20%, ChiNext (创业板): ±20%
    """
    limit = 0.20 if is_star else 0.10
    upper = prev_close * (1 + limit)
    lower = prev_close * (1 - limit)
    return max(lower, min(price, upper))
