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


# ═══════════════════════════════════════════════════════════════
# NEW: dual-mode + benchmark charts, correlation heatmap, cost bars
# ═══════════════════════════════════════════════════════════════

def strategy_dual_chart(name: str, eq_equal: pd.Series, eq_adaptive: pd.Series,
                        bench: pd.Series | None = None, sim_start: str = "") -> str:
    """One strategy: equal-weight solid line, adaptive dashed, benchmark gray dash-dot, + drawdown."""
    if eq_equal.empty or len(eq_equal) < 2:
        return ""
    nav_eq = eq_equal / eq_equal.iloc[0]
    nav_ad = eq_adaptive / eq_adaptive.iloc[0] if not eq_adaptive.empty else None
    color = COLORS[hash(name) % len(COLORS)]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 4.6), gridspec_kw={"height_ratios": [3, 1]})

    ax1.plot(nav_eq.index, nav_eq.values, color=color, linewidth=1.8,
             label=f"等权 {((nav_eq.iloc[-1] - 1) * 100):+.1f}%")
    if nav_ad is not None and len(nav_ad) >= 2:
        ax1.plot(nav_ad.index, nav_ad.values, color=color, linewidth=1.4, linestyle="--",
                 label=f"自适应 {((nav_ad.iloc[-1] - 1) * 100):+.1f}%")
    if bench is not None and len(bench) >= 2:
        b = bench.reindex(nav_eq.index).ffill().dropna()
        if len(b) >= 2:
            nb = b / b.iloc[0]
            ax1.plot(nb.index, nb.values, color="#888", linewidth=1.2, linestyle="-.",
                     label=f"CSI500 {((nb.iloc[-1] - 1) * 100):+.1f}%")
    ax1.axhline(y=1.0, color="gray", linestyle=":", alpha=0.4)
    ax1.set_title(f"{name} — 净值走势 (起始 {sim_start})", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=8, loc="best")
    ax1.set_ylabel("净值", fontsize=9)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax1.grid(True, alpha=0.3)

    peak = nav_eq.cummax()
    dd = (nav_eq - peak) / peak * 100
    ax2.fill_between(dd.index, dd.values, 0, color="#d62728", alpha=0.4)
    ax2.plot(dd.index, dd.values, color="#d62728", linewidth=1)
    ax2.set_ylabel("回撤%", fontsize=9)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig_to_base64(fig)


def correlation_heatmap(ret_df: pd.DataFrame, labels: dict[str, str] | None = None,
                        title: str = "策略收益相关性") -> str:
    """Correlation matrix heatmap of strategy daily returns (matplotlib only)."""
    if ret_df.empty or ret_df.shape[1] < 2:
        return ""
    corr = ret_df.corr()
    names = [labels.get(c, c) if labels else c for c in corr.columns]
    n = len(corr)

    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(corr.values, cmap="RdYlGn_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(names, fontsize=9)
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(v) > 0.6 else "#333")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title(title, fontsize=13, fontweight="bold")
    fig.tight_layout()
    return fig_to_base64(fig)


def cost_bar_chart(cost_rows: list[dict]) -> str:
    """Stacked horizontal bars: commission / stamp duty / slippage per strategy."""
    if not cost_rows:
        return ""
    names = [r["label"] for r in cost_rows]
    comm = [r["commission"] for r in cost_rows]
    stamp = [r["stamp_duty"] for r in cost_rows]
    slip = [r["slippage"] for r in cost_rows]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    y = range(len(names))
    b1 = ax.barh(y, comm, color="#4472C4", label="佣金", height=0.6)
    b2 = ax.barh(y, stamp, left=comm, color="#ED7D31", label="印花税", height=0.6)
    left2 = [c + s for c, s in zip(comm, stamp)]
    b3 = ax.barh(y, slip, left=left2, color="#70AD47", label="滑点", height=0.6)
    for i, r in enumerate(cost_rows):
        ax.text(r["total"] + max(1, r["total"] * 0.02), i, f"{r['total']:,.0f}", va="center", fontsize=8)
    ax.set_yticks(list(y)); ax.set_yticklabels(names, fontsize=9)
    ax.invert_yaxis()
    ax.legend(fontsize=9, loc="lower right")
    ax.set_title("模拟期间累计交易成本构成 (等权模式)", fontsize=13, fontweight="bold")
    ax.set_xlabel("元", fontsize=9)
    ax.grid(True, alpha=0.2, axis="x")
    fig.tight_layout()
    return fig_to_base64(fig)
