"""
Report generator — produces Markdown and HTML summary reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def generate_markdown_report(results: list[dict[str, Any]], output_path: str | None = None) -> str:
    """Generate a Markdown comparison report from backtest results."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    if df.empty:
        return "# No results\n"

    lines: list[str] = []
    lines.append("# 量化策略回测对比报告\n")
    lines.append(f"**生成时间**: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## 策略概览\n")
    lines.append("| 策略 | 来源 | Stars | 类别 |")
    lines.append("|------|------|-------|------|")
    for _, row in df.iterrows():
        lines.append(f"| {row.get('strategy','')} | {row.get('source_project','')} | ★ {row.get('source_stars','')} | {row.get('category','')} |")

    lines.append("\n## 回测结果\n")
    lines.append(f"**参数配置**: 初始资金 {1_000_000:,} 元, 单边手续费 0.1%, 滑点 0.1%\n")
    lines.append("| 策略 | 股票池 | 累计收益(%) | Sharpe | 最大回撤(%) | 总交易笔数 |")
    lines.append("|------|--------|------------|--------|------------|-----------|")
    for _, row in df.iterrows():
        ret = row.get("total_return_pct", "N/A")
        sharpe = row.get("sharpe_ratio", "N/A")
        dd = row.get("max_drawdown_pct", "N/A")
        trades = row.get("total_trades", "N/A")
        lines.append(f"| {row.get('strategy','')} | {row.get('pool','')} | {ret} | {sharpe} | {dd} | {trades} |")

    report = "\n".join(lines)
    if output_path:
        p = REPORT_DIR / output_path
        p.write_text(report, encoding="utf-8")
    return report


def generate_html_report(results: list[dict[str, Any]], output_path: str = "report.html") -> str:
    """Generate an HTML comparison report."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)
    html = df.to_html(index=False, border=1, classes="table table-striped", justify="center")

    template = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>量化策略回测报告</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
h1 {{ color: #333; }}
.table {{ border-collapse: collapse; width: 100%%; background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.table th {{ background: #4472C4; color: #fff; padding: 12px 8px; text-align: center; }}
.table td {{ padding: 8px; text-align: center; border-bottom: 1px solid #eee; }}
.table tr:hover {{ background: #f0f4ff; }}
</style>
</head>
<body>
<h1>量化策略回测对比报告</h1>
<p>生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p>
{html}
</body>
</html>"""

    p = REPORT_DIR / output_path
    p.write_text(template, encoding="utf-8")
    return str(p)
