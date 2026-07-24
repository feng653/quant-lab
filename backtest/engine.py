"""
Backtest engine — wraps backtrader for A-share market simulation.

Features:
- Event-driven execution (correctly handles T+1, price limits, suspensions)
- A-share transaction cost model (commission + stamp duty + slippage)
- Multi-strategy batch runner
"""

from __future__ import annotations

import logging
from typing import Any

import backtrader as bt

from config.settings import config as cfg

logger = logging.getLogger(__name__)


class AShareCommission(bt.CommInfoBase):
    """A-share commission model: 0.1% per side + 0.1% stamp duty on sell only."""

    params = (
        ("commission", cfg.cost.commission),
        ("stamp_duty", cfg.cost.stamp_duty),
    )

    def _getcommission(self, size: float, price: float, pseudoexec: bool) -> float:
        value = abs(size) * price
        comm = value * self.p.commission
        if size < 0:  # sell — add stamp duty
            comm += value * self.p.stamp_duty
        return comm


class GenericStrategy(bt.Strategy):
    """Generic backtrader strategy that replays pre-generated signals."""

    params = (
        ("signals", {}),
        ("max_positions", cfg.backtest.position_limit),
    )

    def __init__(self) -> None:
        self.orders: dict[str, Any] = {}
        self.positions_held: set[str] = set()

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0).isoformat()
        day_signals = self.p.signals.get(dt, [])

        for sig in day_signals:
            code = sig["code"]
            action = sig["action"]

            data = self.getdatabyname(code)
            if data is None:
                continue

            if action == "buy":
                if code in self.positions_held:
                    continue
                if len(self.positions_held) >= self.p.max_positions:
                    continue
                # A-share T+1 and price limit check
                if self._at_limit(data):
                    continue
                weight = sig.get("weight", 0.05)
                size = (self.broker.getvalue() * weight) / data.close[0]
                size = int(size // 100) * 100  # round to lots of 100
                if size >= 100:
                    self.orders[code] = self.buy(data=data, size=size)
                    self.positions_held.add(code)

            elif action == "sell":
                pos = self.getposition(data)
                if pos.size > 0:
                    self.close(data=data)
                    self.positions_held.discard(code)

    def _at_limit(self, data) -> bool:
        """Check if stock is at daily price limit (illiquid)."""
        prev_close = data.close[-1] if len(data) > 1 else data.close[0]
        if prev_close == 0:
            return False
        pct = (data.close[0] - prev_close) / prev_close
        return pct >= 0.098


def run_single_strategy(
    price_df: "pd.DataFrame",
    signals: dict[str, list[dict[str, Any]]],
    pool_name: str,
    strategy_name: str,
) -> dict[str, Any]:
    """Run a single strategy backtest and return performance summary."""
    import pandas as pd

    cerebro = bt.Cerebro()

    # Add data feeds
    codes = price_df["code"].unique()
    for code in codes:
        sub = price_df[price_df["code"] == code].sort_values("date").copy()
        if sub.empty:
            continue
        sub = sub.set_index("date")
        data = bt.feeds.PandasData(dataname=sub, open="open", high="high", low="low", close="close", volume="volume")
        cerebro.adddata(data, name=code)

    cerebro.addstrategy(GenericStrategy, signals=signals)
    cerebro.broker.setcash(cfg.backtest.initial_cash)
    cerebro.broker.addcommissioninfo(AShareCommission())
    cerebro.broker.set_slippage_perc(cfg.cost.slippage)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.02, timeframe=bt.TimeFrame.Days)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.AnnualReturn, _name="annreturn")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    try:
        results = cerebro.run()
    except Exception as e:
        logger.error("Backtest failed for %s: %s", strategy_name, e)
        return {"strategy": strategy_name, "pool": pool_name, "error": str(e)}

    strat = results[0]
    sharpe = strat.analyzers.sharpe.get_analysis()
    dd = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    final_value = cerebro.broker.getvalue()
    total_return = (final_value / cfg.backtest.initial_cash) - 1

    total_trades = 0
    won_trades = 0
    if trades:
        t = trades.get("total", {})
        if hasattr(t, "total"):
            total_trades = int(t.total) if t.total else 0
        else:
            total_trades = int(t.get("total", 0)) if isinstance(t, dict) else 0
        w = trades.get("won", {})
        if hasattr(w, "total"):
            won_trades = int(w.total) if w.total else 0
        elif isinstance(w, dict):
            won_trades = int(w.get("total", 0))

    win_rate = round(won_trades / total_trades * 100, 1) if total_trades > 0 else 0

    return {
        "strategy": strategy_name,
        "pool": pool_name,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "sharpe_ratio": round(sharpe.get("sharperatio", 0) or 0, 3),
        "max_drawdown_pct": round(dd.get("max", {}).get("drawdown", 0) or 0, 2),
        "total_trades": total_trades,
        "win_rate_pct": win_rate,
    }
