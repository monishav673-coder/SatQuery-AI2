"""
SATQUERY AI — Queue Service
Enqueues analysis jobs on the RQ queue when Redis is available.
Falls back to synchronous in-process execution when Redis is absent
(useful for local development without Redis).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)

_redis_client = None
_queue        = None
_initialized  = False


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(url, socket_connect_timeout=2)
        _redis_client.ping()
        logger.info("Queue service: Redis connected at %s", url)
    except Exception as e:
        logger.info("Queue service: Redis unavailable (%s). Sync fallback active.", e)
        _redis_client = None
    return _redis_client


def _get_queue():
    global _queue
    if _queue is not None:
        return _queue
    r = _get_redis()
    if r is None:
        return None
    try:
        from rq import Queue
        _queue = Queue("analysis", connection=r)
    except ImportError:
        logger.info("rq not installed. Sync fallback active.")
        _queue = None
    return _queue


def enqueue_analysis(
    analysis_id: str,
    mode: str,
    image1_path: Optional[str],
    image2_path: Optional[str],
    latitude: Optional[float],
    longitude: Optional[float],
    place_name: Optional[str],
    before_date: Optional[str],
    after_date: Optional[str],
    obs_date: Optional[str],
    imagery_info: Optional[dict],
    nl_query: Optional[str],
) -> dict:
    """
    Enqueue an analysis job.
    Returns {"queued": True, "job_id": "..."} or {"queued": False, "reason": "..."}.
    """
    q = _get_queue()
    if q is not None:
        try:
            from worker.analysis_job import run_analysis_job
            job = q.enqueue(
                run_analysis_job,
                analysis_id=analysis_id,
                mode=mode,
                image1_path=image1_path,
                image2_path=image2_path,
                latitude=latitude,
                longitude=longitude,
                place_name=place_name,
                before_date=before_date,
                after_date=after_date,
                obs_date=obs_date,
                imagery_info=imagery_info,
                nl_query=nl_query,
                redis_url=os.environ.get("REDIS_URL"),
                job_timeout=int(os.environ.get("ANALYSIS_JOB_TIMEOUT", "600")),
            )
            logger.info("Enqueued analysis job %s (job_id=%s)", analysis_id, job.id)
            return {"queued": True, "job_id": job.id}
        except Exception as exc:
            logger.warning("Enqueue failed: %s — falling back to sync", exc)

    # ── Synchronous fallback (no Redis / no rq) ────────────────────────────
    logger.info("Running analysis %s synchronously (no queue)", analysis_id)
    return {"queued": False, "reason": "Redis not available — running synchronously."}


def get_job_status(job_id: str) -> Optional[dict]:
    """Return RQ job status dict, or None if unavailable."""
    q = _get_queue()
    if q is None:
        return None
    try:
        from rq.job import Job
        r = _get_redis()
        job = Job.fetch(job_id, connection=r)
        return {
            "job_id": job.id,
            "status": job.get_status().value,
            "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "exc_info": job.exc_info,
        }
    except Exception:
        return None


def is_redis_available() -> bool:
    return _get_redis() is not None
