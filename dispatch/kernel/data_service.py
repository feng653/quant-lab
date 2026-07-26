"""Kernel data access — re-exports the unified data service.

The fetch/cache logic lives in ``services/data_service.py`` and is already
Flask-free, so the kernel layer re-exports it rather than duplicating it.
Import from here in new code; the old path stays valid.
"""

from services.data_service import (  # noqa: F401
    CACHE_DIR,
    BENCH_SYMBOL,
    trading_days,
    is_trading_day,
    latest_completed_trading_day,
    pool_file,
    load_pool,
    auto_update,
    load_benchmark,
)

__all__ = ["CACHE_DIR", "BENCH_SYMBOL", "trading_days", "is_trading_day",
           "latest_completed_trading_day", "pool_file", "load_pool",
           "auto_update", "load_benchmark"]
