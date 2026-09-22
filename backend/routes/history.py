"""
SATQUERY AI — Analysis History Routes
GET /api/analysis/history
GET /api/analysis/<id>
DELETE /api/analysis/<id>
"""

import json

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.models import db, Analysis

history_bp = Blueprint("history", __name__)


@history_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(5, int(request.args.get("per_page", 20))))

    pagination = (
        Analysis.query
        .filter_by(user_id=user_id)
        .order_by(Analysis.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    items = [a.to_dict(include_result=False) for a in pagination.items]

    return jsonify({
        "success": True,
        "analyses": items,
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    }), 200


@history_bp.route("/<analysis_id>", methods=["GET"])
@jwt_required()
def get_analysis(analysis_id):
    user_id = get_jwt_identity()
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    return jsonify({
        "success": True,
        "analysis": analysis.to_dict(include_result=True),
    }), 200


@history_bp.route("/<analysis_id>", methods=["DELETE"])
@jwt_required()
def delete_analysis(analysis_id):
    user_id = get_jwt_identity()
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    db.session.delete(analysis)
    db.session.commit()
    return jsonify({"success": True, "message": "Analysis deleted."}), 200
