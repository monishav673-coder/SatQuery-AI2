"""
SATQUERY AI — Background Analysis Job
Executed by RQ worker. Heavy ML inference runs here, not in the Flask request thread.

Job lifecycle:
  QUEUED → PROCESSING → VALIDATING → COMPLETED | FAILED

Progress is broadcast via Redis pub/sub so the SSE endpoint can stream it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Ensure backend package is importable from worker context ──────────────────
_backend = os.path.join(os.path.dirname(__file__), "..", "backend")
_root    = os.path.join(os.path.dirname(__file__), "..")
for p in (_backend, _root):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─────────────────────────────────────────────────────────────────────────────
# Progress broadcaster
# ─────────────────────────────────────────────────────────────────────────────

def _publish_progress(
    redis_client,
    analysis_id: str,
    stage: str,
    pct: int,
    message: str,
) -> None:
    """Push progress event onto the Redis channel for the SSE endpoint to consume."""
    if redis_client is None:
        return
    try:
        payload = json.dumps({
            "analysis_id": analysis_id,
            "stage": stage,
            "pct": pct,
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        redis_client.publish(f"analysis:{analysis_id}:progress", payload)
    except Exception as e:
        logger.debug("Progress publish failed (non-fatal): %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Main job entry-point
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_job(
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
    redis_url: Optional[str] = None,
) -> dict:
    """
    Entry-point called by the RQ worker.
    Returns the complete result dict (also persisted to DB inside this function).
    """
    redis_client = _get_redis(redis_url)

    STAGES = [
        ("input_validation",   5,  "Validating inputs…"),
        ("preprocessing",     15,  "Preprocessing imagery…"),
        ("modality",          20,  "Identifying modality…"),
        ("landcover",         35,  "Analysing land cover…"),
        ("buildings",         45,  "Detecting buildings…"),
        ("water",             55,  "Analysing water bodies…"),
        ("agriculture",       62,  "Detecting agricultural areas…"),
        ("change_detection",  72,  "Running change detection…"),
        ("evidence",          82,  "Generating visual evidence…"),
        ("confidence",        90,  "Estimating confidence…"),
        ("nlp",               95,  "Processing natural language query…"),
        ("report_prep",       99,  "Preparing report…"),
    ]

    def progress(idx: int, extra: str = "") -> None:
        stage, pct, msg = STAGES[idx]
        _publish_progress(redis_client, analysis_id, stage, pct, extra or msg)

    # ── Import here so the worker process picks up the right app context ──
    from app import create_app
    from database.models import db, Analysis

    app = create_app()
    with app.app_context():
        analysis = Analysis.query.get(analysis_id)
        if not analysis:
            logger.error("Job: analysis %s not found in DB", analysis_id)
            return {"error": "Analysis record not found."}

        try:
            # Mark processing
            analysis.status = "processing"
            db.session.commit()
            progress(0)

            # ── Run the pipeline ───────────────────────────────────────
            from agents.orchestrator import run_analysis_pipeline

            result = run_analysis_pipeline(
                mode=mode,
                image1_path=image1_path,
                image2_path=image2_path,
                latitude=latitude,
                longitude=longitude,
                place_name=place_name,
                obs_date=obs_date,
                before_date=before_date,
                after_date=after_date,
                imagery_info=imagery_info,
                nl_query=nl_query,
                analysis_id=analysis_id,
                progress_callback=lambda idx, msg="": progress(idx, msg),
            )

            # ── Persist result ─────────────────────────────────────────
            analysis.status            = "completed"
            analysis.result_json       = json.dumps(result)
            analysis.overall_confidence = result.get("overall_confidence")
            analysis.nl_answer         = result.get("nl_answer")
            analysis.completed_at      = datetime.now(timezone.utc)
            db.session.commit()

            # Final progress event
            _publish_progress(
                redis_client, analysis_id, "completed", 100,
                "Analysis complete.",
            )
            logger.info("Job completed: %s", analysis_id)
            return result

        except Exception as exc:
            logger.exception("Job failed for analysis %s", analysis_id)
            analysis.status        = "failed"
            analysis.error_message = str(exc)
            db.session.commit()
            _publish_progress(
                redis_client, analysis_id, "failed", 0,
                f"Analysis failed: {exc}",
            )
            return {"error": str(exc)}


def _get_redis(redis_url: Optional[str]):
    """Return a Redis client or None if Redis is unavailable."""
    try:
        import redis as redis_lib
        url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        client = redis_lib.from_url(url, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception as e:
        logger.debug("Redis unavailable (progress streaming disabled): %s", e)
        return None
