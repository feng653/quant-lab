"""
MiniQMT (xtquant) execution provider — reserved for future paper/live trading.

Requirements:
- Broker account with MiniQMT access (~10万 minimum)
- Windows environment (QMT is Windows-only)
- xtquant Python library installed

Usage:
    1. Open MiniQMT terminal
    2. Set up paper trading account
    3. provider = XtquantProvider()
    4. provider.connect()
    5. Use dispatch_signals() to route strategy signals

Docs: https://dict.thinktrader.net
"""

from __future__ import annotations

import logging
from typing import Any

from execution.base import ExecutionProvider

logger = logging.getLogger(__name__)


class XtquantProvider(ExecutionProvider):
    """MiniQMT paper trading provider (reserved)."""

    def __init__(self) -> None:
        self._connected = False
        self._positions: dict[str, dict[str, Any]] = {}

    def connect(self) -> None:
        """Connect to MiniQMT terminal.

        Example (requires xtquant installed):
            from xtquant import xtdata, xttrader
            self._session = xttrader.XtQuantTrader(path, session_id)
            self._session.start()
            self._connected = True
        """
        logger.info("MiniQMT: connection reserved for future use")
        logger.info("MiniQMT: requires broker account + xtquant library on Windows")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def submit_order(self, code: str, action: str, quantity: int, price: float | None = None) -> dict[str, Any]:
        """Submit order via xtquant.

        Example:
            from xtquant.xttype import StockAccount
            account = StockAccount("account_id")
            # order using self._session.order_stock(...)
        """
        logger.info("MiniQMT stub: %s %s x %d", action, code, quantity)
        return {"status": "pending", "provider": "xtquant", "code": code}

    def get_positions(self) -> dict[str, dict[str, Any]]:
        return self._positions

    def get_account(self) -> dict[str, Any]:
        return {"provider": "xtquant", "status": "reserved"}
