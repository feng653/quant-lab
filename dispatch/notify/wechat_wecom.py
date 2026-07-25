"""
WeCom (企业微信) group bot notification — official Tencent channel, no 3rd party.

Setup (10 min):
  1. Install 企业微信 App, register as personal team (any org name, no verification)
  2. Create a group → 群设置 → 群机器人 → 添加 → copy webhook URL
  3. Put it in .env:  WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...

Messages travel only through Tencent's servers (same trust level as WeChat
itself). Nothing passes any third-party relay.

Falls back silently when WECOM_WEBHOOK_URL is absent.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
MAX_MD_LEN = 3800  # WeCom markdown message limit is 4096 bytes


def _get_webhook() -> str:
    if os.environ.get("WECOM_WEBHOOK_URL"):
        return os.environ["WECOM_WEBHOOK_URL"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("WECOM_WEBHOOK_URL") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def send_wecom_markdown(content: str) -> bool:
    """Send a markdown message to the WeCom group bot. False if not configured."""
    url = _get_webhook()
    if not url:
        logger.info("WECOM_WEBHOOK_URL not configured, skipping WeCom push")
        return False
    if len(content.encode("utf-8")) > MAX_MD_LEN:
        content = content[:MAX_MD_LEN] + "\n\n> …(内容过长已截断, 详见邮件)"
    try:
        import requests
        r = requests.post(url, json={"msgtype": "markdown", "markdown": {"content": content}}, timeout=15)
        ok = r.status_code == 200 and r.json().get("errcode") == 0
        logger.info("WeCom push: %s", "OK" if ok else f"FAIL {r.text[:200]}")
        return ok
    except Exception as e:
        logger.error("WeCom push failed: %s", e)
        return False


def build_daily_wecom(ctx: dict) -> str:
    """Compact markdown daily summary for the WeCom group."""
    state = ctx["state"]; m = ctx["market"]
    keys = sorted([k for k in state["strategies"] if not state["strategies"][k].get("disabled")],
                  key=lambda k: state["strategies"][k]["equal"]["sharpe"], reverse=True)
    bench = state["strategies"][keys[0]]["equal"]["bench_ret"] if keys else 0
    lines = [f"## 📊 量化日报 {ctx['latest_date']}",
             f"> 市场: {m['label']} | 模拟起始 {ctx['sim_start']} ({ctx['n_days']}日) | 基准 {bench:+.2f}%", ""]
    for k in keys:
        e = state["strategies"][k]["equal"]
        ret = e["total_return"]
        color = "info" if ret >= 0 else "warning"
        lines.append(f"> {state['strategies'][k]['label']}: <font color=\"{color}\">{ret:+.2f}%</font> "
                     f"(S {e['sharpe']:+.2f})")
    lines += ["", "> 完整报告见邮件 | 仪表盘 http://localhost:8600"]
    return "\n".join(lines)
