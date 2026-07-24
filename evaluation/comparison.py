"""
Comparison module — cross-strategy, cross-pool analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.metrics import compare_strategies
from evaluation.report import generate_markdown_report, generate_html_report


def run_comparison(results: list[dict[str, Any]], output_dir: str | None = None) -> dict[str, str]:
    """Run full comparison analysis and generate reports.

    Returns paths to generated report files.
    """
    df = compare_strategies(results)

    md = generate_markdown_report(results, "comparison_report.md")
    html = generate_html_report(results, "comparison_report.html")

    output: dict[str, str] = {
        "markdown": str(Path("reports") / "comparison_report.md"),
        "html": str(Path("reports") / "comparison_report.html"),
    }

    # Per-pool breakdown
    for pool in df["pool"].unique():
        pool_results = [r for r in results if r.get("pool") == pool]
        generate_markdown_report(pool_results, f"report_{pool}.md")

    return output


def rank_by_metric(results: list[dict[str, Any]], metric: str = "sharpe_ratio") -> pd.DataFrame:
    """Rank strategies by a given metric across pools."""
    df = pd.DataFrame(results)
    return df.sort_values(["pool", metric], ascending=[True, False])
