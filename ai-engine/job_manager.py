import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from models import AnalysisJob

TERMINAL_STATUSES = frozenset({"succeeded", "failed"})
logger = logging.getLogger(__name__)


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value) if value else None


class JobManager:
    """Small in-process job coordinator for long-running admin operations."""

    def __init__(
        self, max_workers: int = 2, max_history: int = 500, session_factory=None
    ):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_history = max_history
        self._session_factory = session_factory
        self._jobs = {}
        self._lock = Lock()

    def submit(self, operation: str, task) -> str:
        job_id = uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "operation": operation,
                "status": "queued",
                "submitted_at": _timestamp(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }
            self._prune_history()
        self._persist_create(job_id, operation)
        self._executor.submit(self._run, job_id, task)
        return job_id

    def get(self, job_id: str):
        if self._session_factory:
            return self._get_persisted(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def shutdown(self):
        self._executor.shutdown(wait=True)

    def _run(self, job_id: str, task):
        self._update(job_id, status="running", started_at=_timestamp())
        try:
            result = task()
        except Exception:
            logger.exception("Background job failed. job_id=%s", job_id)
            self._update(
                job_id,
                status="failed",
                finished_at=_timestamp(),
                error="작업 실행에 실패했습니다.",
            )
            return
        self._update(
            job_id,
            status="succeeded",
            finished_at=_timestamp(),
            result=result,
        )

    def _update(self, job_id: str, **changes):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)
        self._persist_update(job_id, changes)

    def _persist_create(self, job_id, operation):
        if not self._session_factory:
            return
        db = self._session_factory()
        try:
            db.add(
                AnalysisJob(
                    id=job_id,
                    operation=operation,
                    status="queued",
                    submitted_at=datetime.now(timezone.utc),
                )
            )
            db.commit()
        finally:
            db.close()

    def _persist_update(self, job_id, changes):
        if not self._session_factory:
            return
        db = self._session_factory()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if job:
                for key, value in changes.items():
                    setattr(
                        job, key, _as_datetime(value) if key.endswith("_at") else value
                    )
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to persist job state. job_id=%s", job_id)
        finally:
            db.close()

    def _get_persisted(self, job_id):
        db = self._session_factory()
        try:
            job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
            if not job:
                return None
            return {
                "job_id": job.id,
                "operation": job.operation,
                "status": job.status,
                "submitted_at": _format_datetime(job.submitted_at),
                "started_at": _format_datetime(job.started_at),
                "finished_at": _format_datetime(job.finished_at),
                "result": job.result,
                "error": job.error,
            }
        finally:
            db.close()

    def _prune_history(self):
        terminal_jobs = [
            job for job in self._jobs.values() if job["status"] in TERMINAL_STATUSES
        ]
        overflow = len(terminal_jobs) - self._max_history
        if overflow <= 0:
            return
        for job in sorted(terminal_jobs, key=lambda item: item["submitted_at"])[
            :overflow
        ]:
            self._jobs.pop(job["job_id"], None)


def _format_datetime(value):
    return value.isoformat() if value else None
