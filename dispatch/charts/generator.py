"""
Chart generator — matplotlib plots embedded as base64 HTML images.

Generates equity curves, drawdown charts, and strategy comparisons.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

# Chinese font support
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]


def fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return f'<img src="data:image/png;base64,{b64}" style="max-width:100%;border-radius:6px;margin:8px 0">'


def equity_curve_chart(equity_data: dict[str, pd.Series], title: str = "Strategy Equity Curves") -> str:
    """Generate equity curve comparison chart for top strategies."""
    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (name, series) in enumerate(equity_data.items()):
        if series.empty or len(series) < 2:
            continue
        normalized = series / series.iloc[0]
        ax.plot(normalized.index, normalized.values, color=COLORS[i % len(COLORS)], linewidth=1.5, label=name)
    ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5)
    ax.legend(fontsize=9, loc="upper left")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_ylabel("Normalized NAV", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)


def drawdown_chart(equity_data: dict[str, pd.Series], title: str = "Drawdown Curves") -> str:
    """Generate drawdown comparison chart."""
    fig, ax = plt.subplots(figsize=(10, 4))
    for i, (name, series) in enumerate(equity_data.items()):
        if series.empty or len(series) < 2:
            continue
        peak = series.cummax()
        dd = (series - peak) / peak * 100
        ax.fill_between(dd.index, dd.values, 0, color=COLORS[i % len(COLORS)], alpha=0.3, label=name)
        ax.plot(dd.index, dd.values, color=COLORS[i % len(COLORS)], linewidth=1)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_ylabel("Drawdown %", fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=min(ax.get_ylim()[0], -40))
    fig.tight_layout()
    return fig_to_base64(fig)


def monthly_return_heatmap(equity_data: dict[str, pd.Series]) -> str:
    """Generate monthly return heatmap for top 4 strategies."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 6))
    strategies = list(equity_data.items())[:4]
    for idx, (name, series) in enumerate(strategies):
        ax = axes[idx // 2][idx % 2]
        if series.empty or len(series) < 20:
            continue
        rets = series.pct_change().dropna()
        monthly = rets.resample("ME").apply(lambda x: (1 + x).prod() - 1)
        years = sorted(set(monthly.index.year))
        months = range(1, 13)
        data = np.full((len(years), 12), np.nan)
        for i, y in enumerate(years):
            for m in months:
                dt = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
                if dt in monthly.index:
                    data[i][m - 1] = monthly[dt] * 100
        im = ax.imshow(data, cmap="RdYlGn", aspect="auto", vmin=-15, vmax=15)
        ax.set_xticks(range(12))
        ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"], fontsize=8)
        ax.set_yticks(range(len(years)))
        ax.set_yticklabels([str(y) for y in years], fontsize=8)
        ax.set_title(name, fontsize=10, fontweight="bold")
        for i in range(len(years)):
            for j in range(12):
                if not np.isnan(data[i][j]):
                    ax.text(j, i, f"{data[i][j]:.0f}", ha="center", va="center", fontsize=6)
    fig.tight_layout()
    return fig_to_base64(fig)


def strategy_single_chart(name: str, series: pd.Series, title: str = "") -> str:
    """Generate a single strategy's equity curve + drawdown chart."""
    if series.empty or len(series) < 2:
        return ""
    normalized = series / series.iloc[0]
    peak = normalized.cummax()
    dd = (normalized - peak) / peak * 100
    ret = (normalized.iloc[-1] - 1) * 100

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 4), gridspec_kw={"height_ratios": [3, 1]})
    color = COLORS[hash(name) % len(COLORS)]

    ax1.plot(normalized.index, normalized.values, color=color, linewidth=1.8, label=f"{name} 净值")
    ax1.axhline(y=1.0, color="gray", linestyle="--", alpha=0.4)
    ax1.fill_between(normalized.index, 1.0, normalized.values, where=normalized.values > 1.0, color=color, alpha=0.15)
    ax1.fill_between(normalized.index, normalized.values, 1.0, where=normalized.values < 1.0, color="#d62728", alpha=0.1)
    ax1.set_title(title or f"{name} — 净值走势 (收益 {ret:+.1f}%)", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=9, loc="upper left")
    ax1.set_ylabel("净值", fontsize=9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(dd.index, dd.values, 0, color="#d62728", alpha=0.4)
    ax2.plot(dd.index, dd.values, color="#d62728", linewidth=1)
    ax2.set_ylabel("回撤%", fontsize=9)
    ax2.set_ylim(bottom=min(dd.min() * 1.2, -40), top=5)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig_to_base64(fig)


def strategy_grid_charts(equity_data: dict[str, pd.Series], title: str = "") -> str:
    """Generate a grid of individual strategy charts."""
    if not equity_data:
        return ""
    html_parts = ['<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center">']
    for name, series in equity_data.items():
        chart = strategy_single_chart(name, series)
        if chart:
            html_parts.append(f'<div style="flex:1;min-width:480px;max-width:600px">{chart}</div>')
    html_parts.append("</div>")
    return "\n".join(html_parts)
    """Generate horizontal bar chart comparing strategy metrics."""
    fig, ax = plt.subplots(figsize=(8, 5))
    sorted_results = sorted([r for r in results if r.get(metric, 0) != 0], key=lambda x: x.get(metric, 0))
    names = [f"{r['strategy']} ({r['pool']})" for r in sorted_results]
    values = [r.get(metric, 0) for r in sorted_results]
    colors_bar = ["#2ca02c" if v > 0 else "#d62728" for v in values]
    bars = ax.barh(names, values, color=colors_bar, edgecolor="white", height=0.6)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + (0.5 if val >= 0 else -2), bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=8,
                color="#2ca02c" if val >= 0 else "#d62728")
    ax.axvline(x=0, color="gray", linewidth=0.5)
    ax.set_title(title or f"Strategy {metric}", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.2, axis="x")
    fig.tight_layout()
    return fig_to_base64(fig)
