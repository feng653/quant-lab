"""
Execution layer — abstract interface for paper/live trading.

All backtest strategies output signals. The execution layer
receives signals and routes them to the correct broker.

Swap the implementation to change from paper → live trading
without touching strategy code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExecutionProvider(ABC):
    """Abstract execution interface."""

    @abstractmethod
    def submit_order(self, code: str, action: str, quantity: int, price: float | None = None) -> dict[str, Any]: ...

    @abstractmethod
    def get_positions(self) -> dict[str, dict[str, Any]]: ...

    @abstractmethod
    def get_account(self) -> dict[str, Any]: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...


def dispatch_signals(
    signals: dict[str, list[dict[str, Any]]],
    provider: ExecutionProvider,
) -> list[dict[str, Any]]:
    """Dispatch a day's signals through the given execution provider."""
    results: list[dict[str, Any]] = []
    for date_str, entries in sorted(signals.items()):
        for sig in entries:
            r = provider.submit_order(sig["code"], sig["action"], sig.get("quantity", 100))
            results.append(r)
    return results
