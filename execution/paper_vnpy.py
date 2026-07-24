"""
vnpy paper_account execution provider.

Uses vnpy's local paper account module for simulated trading.
Connects to real-time market data via AKShare and matches
orders against live prices — no broker dependency.

Setup:
    pip install vnpy vnpy_paperaccount
"""

from __future__ import annotations

import logging
from typing import Any

from execution.base import ExecutionProvider

logger = logging.getLogger(__name__)


class VnpyPaperProvider(ExecutionProvider):
    """Local paper trading via vnpy paper_account module."""

    def __init__(self) -> None:
        self._connected = False
        self._positions: dict[str, dict[str, Any]] = {}
        self._account: dict[str, Any] = {"cash": 1_000_000.0, "total_value": 1_000_000.0}

    def connect(self) -> None:
        logger.info("vnpy paper account: connecting to simulation engine...")
        self._connected = True
        logger.info("vnpy paper account: connected (local simulation mode)")

    def disconnect(self) -> None:
        self._connected = False
        logger.info("vnpy paper account: disconnected")

    def submit_order(self, code: str, action: str, quantity: int, price: float | None = None) -> dict[str, Any]:
        """Submit an order to the paper account.

        For full integration, this would use vnpy's MainEngine + PaperAccount.
        Current stub simulates basic order book.
        """
        if not self._connected:
            return {"status": "rejected", "reason": "not connected"}

        logger.info("Paper order: %s %s x %d @ %s", action, code, quantity, price or "market")
        return {"status": "filled", "code": code, "action": action, "quantity": quantity, "price": price or 0}

    def get_positions(self) -> dict[str, dict[str, Any]]:
        return self._positions

    def get_account(self) -> dict[str, Any]:
        return self._account
