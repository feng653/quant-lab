"""
AI assistant — natural-language data & task management for the web.

Flow: user text → DeepSeek intent extraction (JSON) → whitelist action
execution → templated Chinese reply. No arbitrary code execution: actions
are a fixed whitelist with schema-checked args.

Actions:
  data_status / update_data / check_missing / list_strategies
  query_trades(strategy, date) / scheduler_status / run_pipeline / help
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

HISTORY_FILE = Path(__file__).resolve().parent.parent / "state" / "assistant_history.json"
MAX_HISTORY = 30

ACTIONS_DOC = """
可用动作(JSON的action字段):
- data_status: 查看数据缓存状态(范围/行数/股票数) args={}
- update_data: 拉取最新行情数据 args={}
- check_missing: 检查最近数据缺失情况 args={}
- list_strategies: 列出全部策略及启用状态 args={}
- query_trades: 查询成交记录 args={"strategy":"可选策略key","date":"可选YYYY-MM-DD"}
- scheduler_status: 查看调度器状态 args={}
- run_pipeline: 立即执行每日pipeline(模拟+邮件) args={}
- help: 列出所有可用动作 args={}
"""


def _history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _append_history(role: str, text: str) -> None:
    h = _history()
    h.append({"role": role, "text": text, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(h[-MAX_HISTORY:], ensure_ascii=False, indent=2), encoding="utf-8")


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()


def _extract_intent(text: str) -> dict:
    """DeepSeek → {"action": ..., "args": {...}}. Falls back to keyword matching."""
    from ai_commentary import _get_api_key, _load_env
    import os
    api_key = _get_api_key()
    if api_key:
        env = _load_env()
        base = (env.get("LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
        model = env.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or "deepseek-v4-flash"
        prompt = f"""你是量化系统的数据管理助手。把用户的自然语言指令映射为一个JSON动作。
{ACTIONS_DOC}
规则: 只输出JSON {{"action":"...","args":{{...}}}}; 无法映射则 {{"action":"help","args":{{}}}};
策略key参考: ma_cross, rsi_reversal, bollinger_breakout, macd_signal, risk_parity, alpha158_lgb_wf, alpha158_xgb_wf, lstm_rank, transformer_rank, alphamaster_gbr
用户指令: {text}"""
        try:
            import requests
            r = requests.post(f"{base}/chat/completions",
                              headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                              json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                    "max_tokens": 200, "temperature": 0.1},
                              timeout=30)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                data = json.loads(m.group(0))
                if "action" in data:
                    return {"action": str(data["action"]), "args": data.get("args", {}) or {}}
        except Exception as e:
            logger.warning("LLM intent failed, fallback to keywords: %s", e)

    t = text.lower()
    if any(k in t for k in ["更新数据", "拉取", "下载", "update"]):
        return {"action": "update_data", "args": {}}
    if any(k in t for k in ["数据状态", "缓存", "多少数据", "status"]):
        return {"action": "data_status", "args": {}}
    if any(k in t for k in ["缺失", "缺数据", "missing"]):
        return {"action": "check_missing", "args": {}}
    if any(k in t for k in ["策略", "strateg"]):
        return {"action": "list_strategies", "args": {}}
    if any(k in t for k in ["成交", "交易记录", "trades"]):
        return {"action": "query_trades", "args": {}}
    if any(k in t for k in ["调度", "定时", "schedule"]):
        return {"action": "scheduler_status", "args": {}}
    if any(k in t for k in ["pipeline", "每日", "跑一下", "执行"]):
        return {"action": "run_pipeline", "args": {}}
    return {"action": "help", "args": {}}


def _execute(action: str, args: dict) -> str:
    """Whitelist execution → Chinese reply text."""
    if action == "data_status":
        from services.data_service import load_pool, pool_file
        df = load_pool("csi500")
        if df.empty:
            return "数据缓存为空。"
        f = pool_file("csi500")
        size = round(f.stat().st_size / 1024 / 1024, 1) if f else 0
        return (f"数据缓存状态：{df['code'].nunique()} 只股票，{len(df):,} 行，"
                f"范围 {df['date'].min():%Y-%m-%d} ~ {df['date'].max():%Y-%m-%d}，文件 {size} MB。")

    if action == "update_data":
        from services.data_service import auto_update
        _, latest, added = auto_update("csi500")
        return f"数据已更新到 {latest}，新增 {added} 个交易日。" if added else f"数据已是最新（{latest}），无需更新。"

    if action == "check_missing":
        from services.data_service import load_pool, trading_days
        df = load_pool("csi500")
        if df.empty:
            return "缓存为空。"
        latest = df["date"].max().strftime("%Y-%m-%d")
        days = trading_days("2026-07-01", latest)
        have = set(df["date"].dt.strftime("%Y-%m-%d").unique())
        missing = [d for d in days if d not in have]
        per_code = df.groupby("code")["date"].count()
        thin = per_code[per_code < len(have) * 0.8]
        return (f"最近交易日 {latest}，7月以来 {len(days)} 个交易日，缺失日期: {missing or '无'}。"
                f"数据覆盖不足80%的股票 {len(thin)} 只。")

    if action == "list_strategies":
        from core.strategies.registry import REGISTRY, is_enabled, scan_strategies
        scan_strategies()
        lines = [f"{'🟢' if is_enabled(k) else '⚪'} {s.label}({k}) — {s.category}, 再平衡{s.rebalance_days}日"
                 for k, s in REGISTRY.items()]
        return "策略库共 %d 个：\n" % len(REGISTRY) + "\n".join(lines)

    if action == "query_trades":
        from services import trade_db
        strategy = args.get("strategy") or None
        date = args.get("date") or None
        df = trade_db.get_trades(strategy=strategy, date=date, limit=20)
        if df.empty:
            return "未查到符合条件的成交记录。"
        df = df.sort_values("date", ascending=False).head(10)
        lines = [f"{t['date']} {t['strategy']} {'买入' if t['action']=='buy' else '卖出'} "
                 f"{t['code']}×{int(t['shares'])} @{t['price']:.2f}" for _, t in df.iterrows()]
        return f"最近 {len(lines)} 条成交：\n" + "\n".join(lines)

    if action == "scheduler_status":
        from services.scheduler import scheduler_status
        st = scheduler_status()
        jobs = "; ".join(f"{j['name']} 下次 {j['next_run']}" for j in st["jobs"]) or "无"
        return (f"调度器{'运行中' if st['running'] else '未运行'}。{jobs}\n"
                f"上次每日pipeline: {st['last_daily']} → {st['last_daily_result']}")

    if action == "run_pipeline":
        from services import job_runner

        def work(job):
            from services.scheduler import daily_pipeline_job
            return daily_pipeline_job(force=True)
        job = job_runner.submit("daily_pipeline", "AI助手触发pipeline", work)
        return f"已启动后台任务 {job.id}（每日pipeline：数据更新→模拟→双邮件），可在任务中心查看进度。"

    return ("我可以帮你：查看/更新数据、检查缺失、列出策略、查成交记录、"
            "看调度状态、触发每日pipeline。例如：'拉取最新数据'、'查看MACD的成交'、'现在跑每日任务'。")


def chat(text: str) -> str:
    """One round of conversation. Returns assistant reply."""
    text = text.strip()
    if not text:
        return "请输入指令。"
    _append_history("user", text)
    intent = _extract_intent(text)
    try:
        reply = _execute(intent["action"], intent.get("args", {}))
    except Exception as e:
        logger.exception("assistant action failed")
        reply = f"执行 {intent['action']} 失败: {e}"
    _append_history("assistant", reply)
    return reply


def get_history() -> list:
    return _history()
