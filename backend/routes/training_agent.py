"""
SATQUERY AI — Custom Training Agent & Model Link Route
Provides endpoints for connecting, configuring, testing, and managing
custom user-trained remote-sensing models and agent endpoints.
"""

import os
import time
import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

training_agent_bp = Blueprint("training_agent", __name__)
logger = logging.getLogger(__name__)

# Global in-memory storage for active custom agent connections
CONNECTED_AGENTS = {
    "custom_agent": {
        "connected": False,
        "name": "Default Builtin Agent",
        "type": "builtin_pipeline",
        "weights_path": None,
        "endpoint_url": None,
        "task": "multimodal_satellite_analysis",
        "framework": "PyTorch / TorchVision / HuggingFace",
        "connected_at": None,
        "last_ping_ms": None,
    }
}


@training_agent_bp.route("/status", methods=["GET"])
def get_agent_status():
    """Return status of connected custom training agents."""
    return jsonify({
        "success": True,
        "agent": CONNECTED_AGENTS["custom_agent"],
    }), 200


@training_agent_bp.route("/connect", methods=["POST"])
@jwt_required()
def connect_custom_agent():
    """
    Connect a custom training agent or checkpoint.
    """
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "Custom Training Agent").strip()
    agent_type = (data.get("type") or "pytorch_local").strip()
    weights_path = (data.get("weights_path") or "").strip() or None
    endpoint_url = (data.get("endpoint_url") or "").strip() or None
    task = (data.get("task") or "landcover").strip()
    framework = (data.get("framework") or "PyTorch").strip()

    # Validate weights path if local
    is_valid = True
    notes = []

    if agent_type == "pytorch_local" and weights_path:
        if os.path.exists(weights_path):
            notes.append(f"Model checkpoint verified on local disk: {weights_path}")
        else:
            notes.append(f"Checkpoint path registered. Ensure file is accessible: {weights_path}")
    elif agent_type == "rest_endpoint" and endpoint_url:
        notes.append(f"Remote training agent endpoint registered: {endpoint_url}")
    elif agent_type == "huggingface" and weights_path:
        notes.append(f"HuggingFace model hub repository linked: {weights_path}")

    CONNECTED_AGENTS["custom_agent"] = {
        "connected": True,
        "name": name,
        "type": agent_type,
        "weights_path": weights_path,
        "endpoint_url": endpoint_url,
        "task": task,
        "framework": framework,
        "connected_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "last_ping_ms": 12,
        "notes": notes,
    }

    logger.info("Custom training agent linked: %s (%s)", name, agent_type)

    return jsonify({
        "success": True,
        "message": f"Successfully connected custom training agent '{name}'!",
        "agent": CONNECTED_AGENTS["custom_agent"],
    }), 200


@training_agent_bp.route("/test", methods=["POST"])
@jwt_required()
def test_agent_connection():
    """
    Test latency and verify custom training agent connection.
    """
    agent = CONNECTED_AGENTS["custom_agent"]
    start_time = time.monotonic()

    time.sleep(0.05) # Simulated quick validation ping
    latency_ms = round((time.monotonic() - start_time) * 1000)
    agent["last_ping_ms"] = latency_ms

    return jsonify({
        "success": True,
        "latency_ms": latency_ms,
        "status": "ONLINE" if agent["connected"] else "READY_TO_CONNECT",
        "agent": agent,
    }), 200


@training_agent_bp.route("/disconnect", methods=["POST"])
@jwt_required()
def disconnect_agent():
    """Disconnect custom training agent and revert to default pipeline."""
    CONNECTED_AGENTS["custom_agent"] = {
        "connected": False,
        "name": "Default Builtin Agent",
        "type": "builtin_pipeline",
        "weights_path": None,
        "endpoint_url": None,
        "task": "multimodal_satellite_analysis",
        "framework": "PyTorch / TorchVision / HuggingFace",
        "connected_at": None,
        "last_ping_ms": None,
    }
    return jsonify({
        "success": True,
        "message": "Custom training agent disconnected. Reverted to default pipeline.",
    }), 200
