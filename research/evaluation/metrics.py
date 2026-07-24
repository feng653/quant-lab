"""
Performance metrics — computes standard quantitative finance metrics.

Used to evaluate and compare strategy backtest results.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def annualized_return(daily_returns: pd.Series, trading_days: int = 252) -> float:
    """Annualized return from daily return series."""
    total = (1 + daily_returns).prod()
    n = len(daily_returns)
    if n == 0:
        return 0.0
    return float(total ** (trading_days / n) - 1)


def annualized_volatility(daily_returns: pd.Series, trading_days: int = 252) -> float:
    """Annualized volatility from daily return series."""
    return float(daily_returns.std() * np.sqrt(trading_days))


def sharpe_ratio(daily_returns: pd.Series, rf: float = 0.02, trading_days: int = 252) -> float:
    """Sharpe ratio: (annualized return - risk-free) / annualized volatility."""
    ann_ret = annualized_return(daily_returns, trading_days)
    ann_vol = annualized_volatility(daily_returns, trading_days)
    if ann_vol == 0:
        return 0.0
    return (ann_ret - rf) / ann_vol


def max_drawdown(daily_returns: pd.Series) -> float:
    """Maximum drawdown from peak."""
    cum = (1 + daily_returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    return float(dd.min())


def calmar_ratio(daily_returns: pd.Series) -> float:
    """Calmar ratio: annualized return / max drawdown."""
    ann_ret = annualized_return(daily_returns)
    mdd = max_drawdown(daily_returns)
    if mdd == 0 or np.isnan(mdd):
        return 0.0
    return ann_ret / abs(mdd)


def win_rate(daily_returns: pd.Series) -> float:
    """Proportion of positive-return days."""
    if len(daily_returns) == 0:
        return 0.0
    return float((daily_returns > 0).sum() / len(daily_returns))


def monthly_returns(daily_returns: pd.Series) -> pd.Series:
    """Aggregate daily returns to monthly."""
    return daily_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1).dropna()


def yearly_returns(daily_returns: pd.Series) -> pd.Series:
    """Aggregate daily returns to yearly."""
    return daily_returns.resample("YE").apply(lambda x: (1 + x).prod() - 1).dropna()


def compute_all_metrics(daily_returns: pd.Series) -> dict[str, Any]:
    """Compute a standard metrics suite from daily returns."""
    return {
        "annual_return_pct": round(annualized_return(daily_returns) * 100, 2),
        "annual_volatility_pct": round(annualized_volatility(daily_returns) * 100, 2),
        "sharpe_ratio": round(sharpe_ratio(daily_returns), 3),
        "max_drawdown_pct": round(max_drawdown(daily_returns) * 100, 2),
        "calmar_ratio": round(calmar_ratio(daily_returns), 3),
        "win_rate_pct": round(win_rate(daily_returns) * 100, 1),
        "total_days": len(daily_returns),
    }


def compare_strategies(results: list[dict[str, Any]]) -> pd.DataFrame:
    """Produce a comparison DataFrame sorted by Sharpe ratio."""
    import pandas as pd

    df = pd.DataFrame(results)
    sort_col = "sharpe_ratio" if "sharpe_ratio" in df.columns else "total_return_pct"
    return df.sort_values(sort_col, ascending=False)
