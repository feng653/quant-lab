"""
Scheduler — APScheduler inside the web service process.

Jobs:
  - daily_pipeline: every trading day 15:35 (data update → simulate → emails → wechat)
  - weekly_cleanup: Sunday 03:00 (mail archive, log rotation, DB vacuum)

A same-day file lock prevents duplicate pipeline runs (manual trigger and
scheduled trigger share it). State is persisted for the /scheduler web page.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
SCHED_STATE_FILE = STATE_DIR / "scheduler_state.json"
RUN_LOCK_FILE = STATE_DIR / "daily_run.lock"

_scheduler = None


def _load_state() -> dict:
    if SCHED_STATE_FILE.exists():
        try:
            return json.loads(SCHED_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(patch: dict) -> None:
    st = _load_state()
    st.update(patch)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SCHED_STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def already_ran_today() -> bool:
    if not RUN_LOCK_FILE.exists():
        return False
    try:
        return RUN_LOCK_FILE.read_text().strip() == datetime.now().strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_ran_today() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUN_LOCK_FILE.write_text(datetime.now().strftime("%Y-%m-%d"))


def daily_pipeline_job(force: bool = False) -> str:
    """The 15:35 job. Returns a short result string."""
    from services.data_service import is_trading_day
    if not force and not is_trading_day():
        msg = "not a trading day, skipped"
        _save_state({"last_daily": datetime.now().isoformat(), "last_daily_result": msg})
        return msg
    if not force and already_ran_today():
        msg = "already ran today, skipped"
        logger.info(msg)
        return msg

    logger.info("═══ daily pipeline start ═══")
    try:
        from run_daily import main as run_daily_main
        run_daily_main(force=True)
        mark_ran_today()
        msg = "OK"
    except Exception as e:
        logger.exception("daily pipeline failed")
        msg = f"FAILED: {e}"
    _save_state({"last_daily": datetime.now().isoformat(), "last_daily_result": msg})
    return msg


def weekly_cleanup_job() -> str:
    try:
        import subprocess
        import sys
        script = Path(__file__).resolve().parent.parent.parent / "scripts" / "cleanup_data.py"
        subprocess.run([sys.executable, str(script)], timeout=600, capture_output=True)
        msg = "OK"
    except Exception as e:
        msg = f"FAILED: {e}"
    _save_state({"last_cleanup": datetime.now().isoformat(), "last_cleanup_result": msg})
    return msg


def start_scheduler() -> object:
    """Start BackgroundScheduler (idempotent). Returns the scheduler."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(daily_pipeline_job, CronTrigger(hour=15, minute=35),
                       id="daily_pipeline", name="每日模拟+邮件", replace_existing=True,
                       misfire_grace_time=3600)
    _scheduler.add_job(weekly_cleanup_job, CronTrigger(day_of_week="sun", hour=3, minute=0),
                       id="weekly_cleanup", name="每周数据清理", replace_existing=True)
    _scheduler.start()
    _save_state({"started_at": datetime.now().isoformat()})
    logger.info("Scheduler started: daily 15:35, weekly Sun 03:00")
    return _scheduler


def scheduler_status() -> dict:
    st = _load_state()
    jobs = []
    if _scheduler is not None:
        for j in _scheduler.get_jobs():
            jobs.append({"id": j.id, "name": j.name,
                         "next_run": j.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if j.next_run_time else "-"})
    return {"running": _scheduler is not None, "jobs": jobs,
            "last_daily": st.get("last_daily", "-"), "last_daily_result": st.get("last_daily_result", "-"),
            "last_cleanup": st.get("last_cleanup", "-"), "started_at": st.get("started_at", "-"),
            "already_ran_today": already_ran_today()}
