"""
SATQUERY AI — SSE Progress Stream
GET /api/analysis/<id>/progress

Streams Server-Sent Events for real-time analysis progress.
The worker publishes events to Redis channel: analysis:<id>:progress
This endpoint subscribes and relays them to the browser.

Falls back to polling the DB status when Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Generator

from flask import Blueprint, Response, stream_with_context, jsonify, current_app, request
from flask_jwt_extended import jwt_required, get_jwt_identity, decode_token

from database.models import Analysis

progress_bp = Blueprint("progress", __name__)
logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.5   # seconds between DB polls when Redis unavailable
_SSE_TIMEOUT   = 600   # maximum seconds to stream (10 min)


@progress_bp.route("/<analysis_id>/progress")
def stream_progress(analysis_id: str):
    # Accept token via header OR query param (EventSource can't set headers)
    auth_header = request.headers.get("Authorization", "")
    token_from_query = request.args.get("token", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif token_from_query:
        token = token_from_query

    if not token:
        return jsonify({"success": False, "error": "Authentication required."}), 401

    try:
        from flask_jwt_extended import decode_token as _decode
        decoded = _decode(token)
        user_id = decoded.get("sub")
        if not user_id:
            raise ValueError("No subject")
    except Exception:
        return jsonify({"success": False, "error": "Invalid or expired token."}), 401

    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    # If already done, return a single completion event immediately
    if analysis.status in ("completed", "failed"):
        def immediate():
            data = json.dumps({
                "analysis_id": analysis_id,
                "stage": analysis.status,
                "pct": 100 if analysis.status == "completed" else 0,
                "message": "Analysis complete." if analysis.status == "completed"
                           else f"Analysis failed: {analysis.error_message or 'unknown error'}",
            })
            yield f"data: {data}\n\n"
        return Response(
            stream_with_context(immediate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Stream via Redis pub/sub or DB polling
    try:
        import redis as redis_lib
        redis_url = current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url, socket_connect_timeout=2)
        r.ping()
        generator = _redis_stream(r, analysis_id, user_id)
    except Exception:
        logger.debug("SSE: Redis unavailable, using DB poll fallback")
        generator = _db_poll_stream(analysis_id, user_id)

    return Response(
        stream_with_context(generator),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _redis_stream(redis_client, analysis_id: str, user_id: str) -> Generator:
    """Subscribe to Redis pub/sub channel and yield SSE events."""
    channel = f"analysis:{analysis_id}:progress"
    pubsub  = redis_client.pubsub()
    pubsub.subscribe(channel)

    deadline = time.time() + _SSE_TIMEOUT
    try:
        for message in pubsub.listen():
            if time.time() > deadline:
                break
            if message["type"] != "message":
                continue
            raw = message["data"]
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            yield f"data: {json.dumps(payload)}\n\n"

            # Stop streaming once terminal state is reached
            if payload.get("stage") in ("completed", "failed"):
                break

            # Heartbeat to keep connection alive
            yield ": heartbeat\n\n"
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception:
            pass


def _db_poll_stream(analysis_id: str, user_id: str) -> Generator:
    """Poll DB status and yield SSE events — fallback when Redis is absent."""
    deadline   = time.time() + _SSE_TIMEOUT
    last_status = None

    while time.time() < deadline:
        analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
        if not analysis:
            break

        status = analysis.status
        if status != last_status:
            pct = {"pending": 2, "processing": 50, "completed": 100, "failed": 0}.get(status, 0)
            payload = json.dumps({
                "analysis_id": analysis_id,
                "stage": status,
                "pct": pct,
                "message": f"Status: {status}",
            })
            yield f"data: {payload}\n\n"
            last_status = status

        if status in ("completed", "failed"):
            break

        # Heartbeat
        yield ": heartbeat\n\n"
        time.sleep(_POLL_INTERVAL)
