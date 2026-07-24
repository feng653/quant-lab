"""
Data maintenance — archive old mail, rotate logs, compact SQLite.

Run weekly (Task Scheduler, e.g. Sunday 03:00):
  python scripts/cleanup_data.py

Policy:
  dispatch/mail/YYYYMM/   older than 6 months → dispatch/mail/archive/
  dispatch/logs/*.log     older than 4 weeks  → delete
  dispatch/state/trades.db→ VACUUM (kept forever)
  state/signals_cache/    ML retrain cache    → kept (deterministic, small)
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DISPATCH = ROOT / "dispatch"


def archive_old_mail(months: int = 6) -> None:
    mail_dir = DISPATCH / "mail"
    archive = mail_dir / "archive"
    cutoff = (datetime.now() - timedelta(days=months * 31)).strftime("%Y%m")
    moved = 0
    for d in mail_dir.iterdir():
        if d.is_dir() and d.name.isdigit() and d.name < cutoff:
            archive.mkdir(exist_ok=True)
            target = archive / d.name
            if target.exists():
                for f in d.iterdir():
                    f.rename(target / f.name)
                d.rmdir()
            else:
                d.rename(target)
            moved += 1
            logger.info("Archived mail %s", d.name)
    logger.info("Mail archive: %d month(s) moved", moved)


def rotate_logs(weeks: int = 4) -> None:
    log_dir = DISPATCH / "logs"
    if not log_dir.exists():
        return
    cutoff = datetime.now() - timedelta(weeks=weeks)
    removed = 0
    for f in log_dir.glob("*.log"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            removed += 1
    logger.info("Log rotation: %d file(s) removed", removed)


def vacuum_db() -> None:
    db = DISPATCH / "state" / "trades.db"
    if not db.exists():
        return
    size_before = db.stat().st_size
    with sqlite3.connect(db) as conn:
        conn.execute("VACUUM")
    logger.info("trades.db VACUUM: %dKB → %dKB", size_before // 1024, db.stat().st_size // 1024)


if __name__ == "__main__":
    archive_old_mail()
    rotate_logs()
    vacuum_db()
    logger.info("Cleanup done")
