"""
WeChat push via PushPlus (pushplus.plus) — free WeChat template messages.

Config via .env or environment:
  PUSHPLUS_TOKEN=your_token   (register at https://www.pushplus.plus)

If token is absent, pushing is silently skipped.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def _get_token() -> str:
    if os.environ.get("PUSHPLUS_TOKEN"):
        return os.environ["PUSHPLUS_TOKEN"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("PUSHPLUS_TOKEN") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def send_wechat(title: str, content_html: str) -> bool:
    """Push an HTML message to WeChat via PushPlus. False if not configured."""
    token = _get_token()
    if not token:
        logger.info("PUSHPLUS_TOKEN not configured, skipping WeChat push")
        return False
    try:
        import requests
        r = requests.post("http://www.pushplus.plus/send", json={
            "token": token, "title": title, "content": content_html,
            "template": "html",
        }, timeout=15)
        ok = r.status_code == 200 and r.json().get("code") == 200
        logger.info("WeChat push: %s", "OK" if ok else f"FAIL {r.text[:200]}")
        return ok
    except Exception as e:
        logger.error("WeChat push failed: %s", e)
        return False
