"""
SATQUERY AI — Image Upload & Analysis Routes
POST /api/analyze/single
POST /api/analyze/optical-sar
POST /api/analyze/multitemporal
"""

import os
import uuid
import json
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from database.models import db, Analysis, UploadedImage
from agents.orchestrator import run_analysis_pipeline
from services.queue_service import enqueue_analysis

analysis_bp = Blueprint("analysis", __name__)

# ── helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


def save_upload(file, role: str) -> tuple[str, dict]:
    """Save uploaded file securely. Returns (stored_path, metadata_dict)."""
    original_name = secure_filename(file.filename)
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
    unique_name = f"{uuid.uuid4().hex}_{role}.{ext}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
    file.save(save_path)

    size = os.path.getsize(save_path)
    width, height = None, None

    # Try to read image dimensions without requiring heavy deps at import time
    try:
        from PIL import Image as PILImage
        with PILImage.open(save_path) as img:
            width, height = img.size
    except Exception:
        pass

    meta = {
        "original_filename": original_name,
        "stored_filename": unique_name,
        "file_size_bytes": size,
        "mime_type": file.content_type,
        "width_px": width,
        "height_px": height,
    }
    return unique_name, meta


def _build_analysis(user_id: str, mode: str, input_type: str = "image") -> Analysis:
    analysis = Analysis(
        user_id=user_id,
        mode=mode,
        input_type=input_type,
        status="pending",
    )
    db.session.add(analysis)
    db.session.flush()   # get the ID before commit
    return analysis


def _attach_image(analysis_id: str, role: str, meta: dict) -> UploadedImage:
    img = UploadedImage(
        analysis_id=analysis_id,
        role=role,
        original_filename=meta["original_filename"],
        stored_filename=meta["stored_filename"],
        file_size_bytes=meta.get("file_size_bytes"),
        mime_type=meta.get("mime_type"),
        width_px=meta.get("width_px"),
        height_px=meta.get("height_px"),
    )
    db.session.add(img)
    return img


# ── single image ──────────────────────────────────────────────────────────────

@analysis_bp.route("/single", methods=["POST"])
@jwt_required()
def analyze_single():
    user_id = get_jwt_identity()
    nl_query = request.form.get("nl_query", "").strip()
    img_lat  = request.form.get("img_lat", "").strip()
    img_lon  = request.form.get("img_lon", "").strip()

    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image file provided."}), 400

    file = request.files["image"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No image file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "error": "Invalid file type. Accepted: JPG, JPEG, PNG, TIFF, GeoTIFF."
        }), 400

    analysis = _build_analysis(user_id, "single", "image")
    analysis.nl_query = nl_query or None

    # Optional user-supplied coordinates for the uploaded image
    if img_lat and img_lon:
        try:
            analysis.latitude  = float(img_lat)
            analysis.longitude = float(img_lon)
            from services.geocoding_service import reverse_geocode
            analysis.place_name = reverse_geocode(analysis.latitude, analysis.longitude)
        except (ValueError, TypeError):
            pass

    stored_name, meta = save_upload(file, "primary")
    analysis.image1_path = stored_name
    _attach_image(analysis.id, "primary", meta)

    db.session.commit()

    analysis.status = "processing"
    db.session.commit()

    # ── Try async queue first; fall back to synchronous ────────────────
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    q_result = enqueue_analysis(
        analysis_id=analysis.id,
        mode="single",
        image1_path=os.path.join(upload_folder, stored_name),
        image2_path=None,
        latitude=analysis.latitude,
        longitude=analysis.longitude,
        place_name=analysis.place_name,
        before_date=None,
        after_date=None,
        obs_date=None,
        imagery_info=None,
        nl_query=nl_query or None,
    )

    if q_result.get("queued"):
        return jsonify({
            "success": True,
            "analysis_id": analysis.id,
            "queued": True,
            "job_id": q_result.get("job_id"),
            "message": "Analysis queued. Poll /api/analysis/<id> or stream /api/analysis/<id>/progress.",
        }), 202

    # Synchronous fallback (no Redis)
    try:
        result = run_analysis_pipeline(
            mode="single",
            image1_path=os.path.join(upload_folder, stored_name),
            latitude=analysis.latitude,
            longitude=analysis.longitude,
            place_name=analysis.place_name,
            nl_query=nl_query or None,
            analysis_id=analysis.id,
        )
        analysis.status            = "completed"
        analysis.result_json       = json.dumps(result)
        analysis.overall_confidence = result.get("overall_confidence")
        analysis.nl_answer         = result.get("nl_answer")
        analysis.completed_at      = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"success": True, "analysis_id": analysis.id, "result": result}), 200
    except Exception as exc:
        analysis.status        = "failed"
        analysis.error_message = str(exc)
        db.session.commit()
        current_app.logger.exception("Single analysis failed for %s", analysis.id)
        return jsonify({"success": False, "error": "Analysis failed.", "detail": str(exc)}), 500


# ── optical + SAR ─────────────────────────────────────────────────────────────

@analysis_bp.route("/optical-sar", methods=["POST"])
@jwt_required()
def analyze_optical_sar():
    user_id = get_jwt_identity()
    nl_query = request.form.get("nl_query", "").strip()
    img_lat  = request.form.get("img_lat", "").strip()
    img_lon  = request.form.get("img_lon", "").strip()

    errors = {}
    if "optical_image" not in request.files:
        errors["optical_image"] = "Optical image is required."
    if "sar_image" not in request.files:
        errors["sar_image"] = "SAR image is required."

    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    optical_file = request.files["optical_image"]
    sar_file = request.files["sar_image"]

    if not allowed_file(optical_file.filename):
        return jsonify({"success": False, "error": "Invalid file type for optical image."}), 400
    if not allowed_file(sar_file.filename):
        return jsonify({"success": False, "error": "Invalid file type for SAR image."}), 400

    analysis = _build_analysis(user_id, "optical_sar", "image")
    analysis.nl_query = nl_query or None

    if img_lat and img_lon:
        try:
            analysis.latitude  = float(img_lat)
            analysis.longitude = float(img_lon)
            from services.geocoding_service import reverse_geocode
            analysis.place_name = reverse_geocode(analysis.latitude, analysis.longitude)
        except (ValueError, TypeError):
            pass

    opt_name, opt_meta = save_upload(optical_file, "optical")
    sar_name, sar_meta = save_upload(sar_file, "sar")
    analysis.image1_path = opt_name
    analysis.image2_path = sar_name
    _attach_image(analysis.id, "optical", opt_meta)
    _attach_image(analysis.id, "sar", sar_meta)

    db.session.commit()

    analysis.status = "processing"
    db.session.commit()

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    q_result = enqueue_analysis(
        analysis_id=analysis.id,
        mode="optical_sar",
        image1_path=os.path.join(upload_folder, opt_name),
        image2_path=os.path.join(upload_folder, sar_name),
        latitude=analysis.latitude,
        longitude=analysis.longitude,
        place_name=analysis.place_name,
        before_date=None, after_date=None, obs_date=None,
        imagery_info=None, nl_query=nl_query or None,
    )
    if q_result.get("queued"):
        return jsonify({
            "success": True, "analysis_id": analysis.id,
            "queued": True, "job_id": q_result.get("job_id"),
            "message": "Analysis queued.",
        }), 202

    try:
        result = run_analysis_pipeline(
            mode="optical_sar",
            image1_path=os.path.join(upload_folder, opt_name),
            image2_path=os.path.join(upload_folder, sar_name),
            latitude=analysis.latitude, longitude=analysis.longitude,
            place_name=analysis.place_name,
            nl_query=nl_query or None, analysis_id=analysis.id,
        )
        analysis.status            = "completed"
        analysis.result_json       = json.dumps(result)
        analysis.overall_confidence = result.get("overall_confidence")
        analysis.nl_answer         = result.get("nl_answer")
        analysis.completed_at      = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"success": True, "analysis_id": analysis.id, "result": result}), 200
    except Exception as exc:
        analysis.status = "failed"; analysis.error_message = str(exc)
        db.session.commit()
        current_app.logger.exception("Optical-SAR analysis failed for %s", analysis.id)
        return jsonify({"success": False, "error": "Analysis failed.", "detail": str(exc)}), 500


# ── multitemporal ─────────────────────────────────────────────────────────────

@analysis_bp.route("/multitemporal", methods=["POST"])
@jwt_required()
def analyze_multitemporal():
    user_id = get_jwt_identity()
    nl_query    = request.form.get("nl_query", "").strip()
    before_date = request.form.get("before_date", "").strip()
    before_time = request.form.get("before_time", "").strip()
    after_date  = request.form.get("after_date", "").strip()
    after_time  = request.form.get("after_time", "").strip()
    img_lat     = request.form.get("img_lat", "").strip()
    img_lon     = request.form.get("img_lon", "").strip()

    errors = {}
    if "before_image" not in request.files:
        errors["before_image"] = "Before image is required."
    if "after_image" not in request.files:
        errors["after_image"] = "After image is required."

    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    before_file = request.files["before_image"]
    after_file  = request.files["after_image"]

    if not allowed_file(before_file.filename):
        return jsonify({"success": False, "error": "Invalid file type for before image."}), 400
    if not allowed_file(after_file.filename):
        return jsonify({"success": False, "error": "Invalid file type for after image."}), 400

    analysis = _build_analysis(user_id, "multitemporal", "image")
    analysis.nl_query    = nl_query or None
    analysis.before_date = before_date or None
    analysis.before_time = before_time or None
    analysis.after_date  = after_date or None
    analysis.after_time  = after_time or None

    if img_lat and img_lon:
        try:
            analysis.latitude  = float(img_lat)
            analysis.longitude = float(img_lon)
            from services.geocoding_service import reverse_geocode
            analysis.place_name = reverse_geocode(analysis.latitude, analysis.longitude)
        except (ValueError, TypeError):
            pass

    before_name, before_meta = save_upload(before_file, "before")
    after_name,  after_meta  = save_upload(after_file,  "after")
    analysis.image1_path = before_name
    analysis.image2_path = after_name
    _attach_image(analysis.id, "before", before_meta)
    _attach_image(analysis.id, "after",  after_meta)

    db.session.commit()

    analysis.status = "processing"
    db.session.commit()

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    q_result = enqueue_analysis(
        analysis_id=analysis.id,
        mode="multitemporal",
        image1_path=os.path.join(upload_folder, before_name),
        image2_path=os.path.join(upload_folder, after_name),
        latitude=analysis.latitude, longitude=analysis.longitude,
        place_name=analysis.place_name,
        before_date=before_date or None, after_date=after_date or None,
        obs_date=None, imagery_info=None, nl_query=nl_query or None,
    )
    if q_result.get("queued"):
        return jsonify({
            "success": True, "analysis_id": analysis.id,
            "queued": True, "job_id": q_result.get("job_id"),
            "message": "Analysis queued.",
        }), 202

    try:
        result = run_analysis_pipeline(
            mode="multitemporal",
            image1_path=os.path.join(upload_folder, before_name),
            image2_path=os.path.join(upload_folder, after_name),
            latitude=analysis.latitude, longitude=analysis.longitude,
            place_name=analysis.place_name,
            before_date=before_date or None, after_date=after_date or None,
            nl_query=nl_query or None, analysis_id=analysis.id,
        )
        analysis.status            = "completed"
        analysis.result_json       = json.dumps(result)
        analysis.overall_confidence = result.get("overall_confidence")
        analysis.nl_answer         = result.get("nl_answer")
        analysis.completed_at      = datetime.now(timezone.utc)
        db.session.commit()
        return jsonify({"success": True, "analysis_id": analysis.id, "result": result}), 200
    except Exception as exc:
        analysis.status = "failed"; analysis.error_message = str(exc)
        db.session.commit()
        current_app.logger.exception("Multitemporal analysis failed for %s", analysis.id)
        return jsonify({"success": False, "error": "Analysis failed.", "detail": str(exc)}), 500
