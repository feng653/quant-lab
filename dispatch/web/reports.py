"""Reports blueprint — daily report archive browsing + latest embedding."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, send_file

bp = Blueprint("reports", __name__)

MAIL_DIR = Path(__file__).resolve().parent.parent / "mail"


def _all_reports() -> list[dict]:
    """All archived report files, newest first."""
    out = []
    if not MAIL_DIR.exists():
        return out
    for month_dir in sorted(MAIL_DIR.iterdir(), reverse=True):
        if not month_dir.is_dir() or not month_dir.name.isdigit():
            continue
        for f in sorted(month_dir.glob("*.html"), reverse=True):
            rtype = "recommend" if f.name.startswith("recommend") else (
                "performance" if f.name.startswith("performance") else "other")
            date_str = f.stem.split("_")[-1]
            out.append({"type": rtype, "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                        "path": f"{month_dir.name}/{f.name}", "size_kb": round(f.stat().st_size / 1024)})
    return sorted(out, key=lambda r: (r["date"], r["type"]), reverse=True)


def latest_report_path(rtype: str) -> Path | None:
    for r in _all_reports():
        if r["type"] == rtype:
            return MAIL_DIR / r["path"]
    return None


@bp.route("/reports")
def reports_list():
    from web.ui.layout import page
    rows = "".join(
        f"<tr><td>{r['date']}</td>"
        f"<td>{'📈 推荐' if r['type']=='recommend' else ('📊 表现' if r['type']=='performance' else r['type'])}</td>"
        f"<td>{r['size_kb']} KB</td>"
        f"<td><a href='/reports/file/{r['path']}' target='_blank'>查看</a></td></tr>"
        for r in _all_reports()) or "<tr><td colspan='4'>暂无报告</td></tr>"
    body = f"""
<div class='card'><h3>📁 每日报告存档</h3>
<p style='color:#666;font-size:12px'>邮件系统每日自动生成推荐+表现两份报告并归档于此，保留全部历史。</p>
<table><tr><th>日期</th><th>类型</th><th>大小</th><th>操作</th></tr>{rows}</table></div>"""
    return page("历史报告", body)


@bp.route("/reports/file/<path:relpath>")
def report_file(relpath: str):
    f = (MAIL_DIR / relpath).resolve()
    if not str(f).startswith(str(MAIL_DIR.resolve())) or not f.exists():
        abort(404)
    return send_file(f)
