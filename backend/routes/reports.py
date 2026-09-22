"""
SATQUERY AI — Report Generation & Download Routes
GET  /api/report/<analysis_id>          → generate (if needed) and stream PDF
POST /api/report/<analysis_id>/generate → explicitly trigger generation
"""

import json
import os

from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.models import db, Analysis
from services.report_service import generate_pdf_report

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/<analysis_id>", methods=["GET"])
@jwt_required()
def download_report(analysis_id):
    user_id = get_jwt_identity()
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    if analysis.status != "completed":
        return jsonify({"success": False, "error": "Analysis has not completed yet."}), 400

    # Generate if not already on disk
    if not analysis.report_path or not os.path.exists(
        os.path.join(current_app.config["REPORTS_FOLDER"], analysis.report_path)
    ):
        result = {}
        if analysis.result_json:
            try:
                result = json.loads(analysis.result_json)
            except Exception:
                result = {}

        report_filename = generate_pdf_report(analysis, result, current_app.config["REPORTS_FOLDER"])
        analysis.report_path = report_filename
        db.session.commit()

    report_full_path = os.path.join(current_app.config["REPORTS_FOLDER"], analysis.report_path)

    if not os.path.exists(report_full_path):
        return jsonify({"success": False, "error": "Report file could not be generated."}), 500

    return send_file(
        report_full_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"SATQUERY_Report_{analysis.id[:8]}.pdf",
    )


@reports_bp.route("/<analysis_id>/generate", methods=["POST"])
@jwt_required()
def generate_report(analysis_id):
    user_id = get_jwt_identity()
    analysis = Analysis.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not analysis:
        return jsonify({"success": False, "error": "Analysis not found."}), 404

    if analysis.status != "completed":
        return jsonify({"success": False, "error": "Analysis must be completed first."}), 400

    result = {}
    if analysis.result_json:
        try:
            result = json.loads(analysis.result_json)
        except Exception:
            result = {}

    try:
        report_filename = generate_pdf_report(analysis, result, current_app.config["REPORTS_FOLDER"])
        analysis.report_path = report_filename
        db.session.commit()
        return jsonify({"success": True, "report_filename": report_filename}), 200
    except Exception as exc:
        current_app.logger.exception("Report generation failed for %s", analysis_id)
        return jsonify({"success": False, "error": "Report generation failed.", "detail": str(exc)}), 500
