"""
SATQUERY AI — Natural Language Query Route
POST /api/query
Body: { "analysis_id": "...", "query": "..." }
"""

import json

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.models import db, Analysis
from agents.orchestrator import answer_natural_language_query

query_bp = Blueprint("query", __name__)


@query_bp.route("", methods=["POST"])
@jwt_required()
def nl_query():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    analysis_id = (data.get("analysis_id") or "").strip()
    query_text = (data.get("query") or "").strip()

    if not analysis_id:
        return jsonify({"success": False, "error": "analysis_id is required."}), 400
    if not query_text:
        return jsonify({"success": False, "error": "query is required."}), 400

    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    if analysis.status != "completed":
        return jsonify({"success": False, "error": "Analysis has not completed yet."}), 400

    result = {}
    if analysis.result_json:
        try:
            result = json.loads(analysis.result_json)
        except Exception:
            result = {}

    answer = answer_natural_language_query(query_text, result)

    # Persist the latest query/answer on the analysis record
    analysis.nl_query = query_text
    analysis.nl_answer = answer
    db.session.commit()

    return jsonify({"success": True, "answer": answer, "query": query_text}), 200
