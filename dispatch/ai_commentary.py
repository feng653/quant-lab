"""
AI market commentary — LLM-generated daily summary (optional).

Reads DeepSeek API key directly from environment variable DEEPSEEK_API_KEY.
Optional overrides via .env or environment:
  LLM_BASE_URL=https://api.deepseek.com/v1   (default)
  LLM_MODEL=deepseek-v4-flash                (default; deepseek-v4-pro also available)

If no API key is found, commentary is silently skipped.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _get_api_key() -> str:
    env = _load_env()
    return (os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY")
            or os.environ.get("LLM_API_KEY") or env.get("LLM_API_KEY") or "")


def generate_commentary(context_text: str, max_tokens: int = 400) -> str | None:
    """Generate 3-5 sentence Chinese market+strategy commentary. None if unavailable."""
    api_key = _get_api_key()
    if not api_key:
        logger.info("DEEPSEEK_API_KEY not configured, skipping AI commentary")
        return None

    env = _load_env()
    base = (env.get("LLM_BASE_URL") or os.environ.get("LLM_BASE_URL")
            or "https://api.deepseek.com/v1").rstrip("/")
    model = env.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or "deepseek-v4-flash"

    prompt = (
        "你是一位客观的量化投资分析师。根据以下今日模拟盘数据，用中文写一段3-5句话的收评，"
        "涵盖: (1)市场状态解读 (2)表现最好和最差的策略及可能原因 (3)一句中性风险提示。"
        "不要给出具体买卖建议，不要使用emoji，语气专业克制。\n\n数据:\n" + context_text
    )

    try:
        import requests
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": 0.4},
            timeout=45,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        return text or None
    except Exception as e:
        logger.warning("AI commentary failed: %s", e)
        return None
