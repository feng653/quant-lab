"""Kernel signal generation — re-exports the signal service.

``services/signal_service.py`` holds the strategy dispatch and signal cache and
has no Flask dependency, so it is re-exported here unchanged.
"""

from services.signal_service import (  # noqa: F401
    generate_all_signals,
    strategy_meta,
)

__all__ = ["generate_all_signals", "strategy_meta"]
