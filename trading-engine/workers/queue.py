"""RQ queue helpers — Redis connection + enqueue + status lookup.

Phase 2 wiring
--------------
Backend (Atlas) imports `enqueue_backtest` to push jobs from the FastAPI
backend. The worker process (`rq worker backtest` in this engine container)
picks them up.

In dev, REDIS_URL defaults to redis://localhost:6379/0. The functions are
import-safe even when `redis` / `rq` is not installed — they raise a clear
error at call time. This lets the synchronous in-process path in server.py
work without Redis for local iteration.
"""
from __future__ import annotations

import os
from typing import Any

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BACKTEST_QUEUE = os.getenv("BACKTEST_QUEUE", "backtest")
JOB_TIMEOUT_SEC = int(os.getenv("BACKTEST_JOB_TIMEOUT_SEC", "1800"))  # 30 min


_redis_conn: Any = None
_queue: Any = None


def _redis() -> Any:
    """Lazy Redis connection."""
    global _redis_conn
    if _redis_conn is not None:
        return _redis_conn
    try:
        from redis import Redis  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "redis package not installed. `uv add redis rq` or use the "
            "in-process path in server.py for dev."
        ) from e
    _redis_conn = Redis.from_url(REDIS_URL)
    return _redis_conn


def _queue_handle() -> Any:
    """Lazy RQ Queue."""
    global _queue
    if _queue is not None:
        return _queue
    try:
        from rq import Queue  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "rq package not installed. `uv add rq` or use the in-process "
            "path in server.py for dev."
        ) from e
    _queue = Queue(BACKTEST_QUEUE, connection=_redis(), default_timeout=JOB_TIMEOUT_SEC)
    return _queue


def enqueue_backtest(
    backtest_id: str,
    strategy_code: str,
    asset: str,
    timeframe: str,
    start: str,
    end: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Push a backtest job onto the `backtest` queue. Returns the RQ job id."""
    q = _queue_handle()
    job = q.enqueue(
        "workers.backtest_worker.run_backtest_job",
        kwargs={
            "backtest_id": backtest_id,
            "strategy_code": strategy_code,
            "asset": asset,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "params": params or {},
        },
        job_id=backtest_id,  # match DB row id so we can look up by either
        result_ttl=86_400,
        failure_ttl=86_400,
    )
    return job.id


def get_status(job_id: str) -> dict[str, Any]:
    """Return a status dict for a previously enqueued job."""
    try:
        from rq.job import Job  # type: ignore
    except ImportError as e:
        raise RuntimeError("rq not installed") from e

    try:
        job = Job.fetch(job_id, connection=_redis())
    except Exception:
        return {"job_id": job_id, "status": "not_found"}

    return {
        "job_id": job_id,
        "status": job.get_status(),
        "result": job.result,
        "exc_info": job.exc_info,
        "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
        "started_at": str(job.started_at) if job.started_at else None,
        "ended_at": str(job.ended_at) if job.ended_at else None,
    }
