"""
Local paper trading — simulated account with position tracking.

Maintains virtual portfolio: cash, positions, trade history.
Reads daily signals from strategies and simulates execution.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "account.json"


class PaperAccount:
    """Local simulated trading account."""

    def __init__(self, initial_cash: float = 1_000_000.0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions: dict[str, dict[str, Any]] = {}
        self.trade_history: list[dict[str, Any]] = []
        self.daily_equity: list[dict[str, Any]] = []
        self._load_state()

    def _load_state(self) -> None:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            self.cash = state.get("cash", self.initial_cash)
            self.positions = state.get("positions", {})
            self.trade_history = state.get("trade_history", [])
            self.daily_equity = state.get("daily_equity", [])

    def save_state(self) -> None:
        with open(STATE_FILE, "w") as f:
            json.dump(
                {
                    "cash": self.cash,
                    "positions": self.positions,
                    "trade_history": self.trade_history[-500:],  # keep last 500
                    "daily_equity": self.daily_equity[-252:],
                    "updated": datetime.now().isoformat(),
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    def get_total_value(self, prices: dict[str, float]) -> float:
        """Mark-to-market total account value."""
        mkt = self.cash
        for code, pos in self.positions.items():
            if code in prices:
                mkt += pos["shares"] * prices[code]
            else:
                mkt += pos["shares"] * pos["avg_cost"]
        return mkt

    def execute_signals(self, signals: dict[str, list[dict]], prices: dict[str, float],
                        commission: float = 0.001, stamp_duty: float = 0.001,
                        slippage: float = 0.001, max_positions: int = 20):
        """Execute a day's signals against current market prices."""
        today_trades: list[dict] = []

        # Process sells first
        for sig in signals:
            if sig["action"] != "sell":
                continue
            code = sig["code"]
            if code not in self.positions:
                continue
            if code not in prices:
                continue
            sell_price = prices[code] * (1 - slippage)
            shares = self.positions[code]["shares"]
            value = shares * sell_price
            cost = value * (commission + stamp_duty)
            self.cash += value - cost
            del self.positions[code]
            trade = {"date": datetime.now().strftime("%Y-%m-%d"), "code": code, "action": "sell",
                     "shares": int(shares), "price": round(sell_price, 2), "value": round(value, 2)}
            today_trades.append(trade)

        # Process buys
        available_codes = [s["code"] for s in signals if s["action"] == "buy" and s["code"] in prices and s["code"] not in self.positions]
        if available_codes and len(self.positions) < max_positions:
            w = 1.0 / len(available_codes)
            for sig in signals:
                if sig["action"] != "buy":
                    continue
                code = sig["code"]
                if code not in available_codes:
                    continue
                buy_price = prices[code] * (1 + slippage)
                allocation = self.cash * w
                shares = int(allocation // buy_price // 100) * 100
                if shares < 100:
                    continue
                cost = shares * buy_price
                self.cash -= cost * (1 + commission)
                self.positions[code] = {"shares": shares, "avg_cost": buy_price, "entered": datetime.now().strftime("%Y-%m-%d")}
                trade = {"date": datetime.now().strftime("%Y-%m-%d"), "code": code, "action": "buy",
                         "shares": int(shares), "price": round(buy_price, 2), "value": round(cost, 2)}
                today_trades.append(trade)
                available_codes.remove(code)

        self.trade_history.extend(today_trades)

        # Record daily equity
        total = self.get_total_value(prices)
        self.daily_equity.append({"date": datetime.now().strftime("%Y-%m-%d"), "value": round(total, 2), "cash": round(self.cash, 2)})
        self.save_state()

        return today_trades

    def summary(self) -> dict[str, Any]:
        """Return account summary."""
        total_val = sum(pos["shares"] * pos["avg_cost"] for pos in self.positions.values())
        return {
            "cash": round(self.cash, 2),
            "position_count": len(self.positions),
            "positions_value": round(total_val, 2),
            "total_value": round(self.cash + total_val, 2),
            "total_return_pct": round((self.cash + total_val) / self.initial_cash * 100 - 100, 2),
            "trade_count_today": sum(1 for t in self.trade_history if t["date"] == datetime.now().strftime("%Y-%m-%d")),
        }
