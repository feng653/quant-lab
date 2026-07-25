"""
Job runner — background thread execution for web-triggered tasks.

Training, backtests, data updates and the daily pipeline all run here so the
Flask process stays responsive. Jobs are in-memory (lost on restart) with a
bounded history; long artifacts are persisted by the tasks themselves.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_HISTORY = 50


class Job:
    def __init__(self, job_type: str, title: str):
        self.id = uuid.uuid4().hex[:8]
        self.type = job_type
        self.title = title
        self.status = "pending"      # pending | running | done | failed
        self.created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.started = ""
        self.finished = ""
        self.log_lines: list[str] = []
        self.result: Any = None
        self.error = ""

    def log(self, msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        self.log_lines.append(line)
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "title": self.title, "status": self.status,
                "created": self.created, "started": self.started, "finished": self.finished,
                "log": self.log_lines[-80:], "error": self.error,
                "has_result": self.result is not None}


class _LogHandler(logging.Handler):
    def __init__(self, job: Job):
        super().__init__()
        self.job = job

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.job.log(self.format(record))
        except Exception:
            pass


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def list_jobs() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.created, reverse=True)


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def submit(job_type: str, title: str, fn: Callable[[Job], Any]) -> Job:
    """Run fn(job) in a daemon thread; job.log() + root logger are captured."""
    job = Job(job_type, title)
    with _lock:
        _jobs[job.id] = job
        if len(_jobs) > MAX_HISTORY:
            for old in sorted(_jobs.values(), key=lambda j: j.created)[: len(_jobs) - MAX_HISTORY]:
                _jobs.pop(old.id, None)

    def _run():
        job.status = "running"
        job.started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        handler = _LogHandler(job)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            job.result = fn(job)
            job.status = "done"
        except Exception as e:
            job.status = "failed"
            job.error = f"{e}\n{traceback.format_exc(limit=5)}"
            job.log(f"FAILED: {e}")
        finally:
            root.removeHandler(handler)
            job.finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=_run, daemon=True, name=f"job-{job.id}").start()
    return job
