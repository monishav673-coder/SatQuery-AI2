"""
SATQUERY AI — Coordinate-Based Analysis Routes
POST /api/analyze/coordinates
POST /api/analyze/coordinates/multitemporal
"""

import json
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from database.models import db, Analysis
from agents.orchestrator import run_analysis_pipeline
from services.geocoding_service import reverse_geocode
from services.satellite_service import fetch_satellite_imagery, download_satellite_tile_image

coordinates_bp = Blueprint("coordinates", __name__)


def _validate_coords(lat, lon):
    errors = {}
    try:
        lat = float(lat)
    except (TypeError, ValueError):
        errors["latitude"] = "Latitude must be a number."
        return None, None, errors
    try:
        lon = float(lon)
    except (TypeError, ValueError):
        errors["longitude"] = "Longitude must be a number."
        return None, None, errors

    if not (-90 <= lat <= 90):
        errors["latitude"] = "Latitude must be between -90 and 90."
    if not (-180 <= lon <= 180):
        errors["longitude"] = "Longitude must be between -180 and 180."
    return lat, lon, errors


# ── preview satellite imagery by coordinates (Single or 2 Years) ─────────────

@coordinates_bp.route("/coordinates/preview", methods=["POST"])
@jwt_required()
def preview_coordinates_satellite():
    data = request.get_json(silent=True) or {}
    mode = (data.get("mode") or "single").lower()

    lat, lon, errors = _validate_coords(data.get("latitude"), data.get("longitude"))
    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    place_name = reverse_geocode(lat, lon)

    if mode == "multitemporal":
        before_date = (data.get("before_date") or "2020-01-01").strip()
        after_date = (data.get("after_date") or "2024-01-01").strip()

        before_year = None
        after_year = None
        try:
            before_year = int(before_date.split("-")[0])
        except Exception:
            before_year = 2020
        try:
            after_year = int(after_date.split("-")[0])
        except Exception:
            after_year = 2024

        before_tile = download_satellite_tile_image(lat, lon, zoom=16, year=before_year, prefix="sat_multitemp_before")
        after_tile = download_satellite_tile_image(lat, lon, zoom=16, year=after_year, prefix="sat_multitemp_after")

        before_img = {
            "available": before_tile.get("success", False),
            "thumbnail_url": before_tile.get("url"),
            "image_path": before_tile.get("filepath"),
            "resolution": before_tile.get("resolution", "0.5m - 2.5m GSD"),
            "dimensions": before_tile.get("dimensions", "512 × 512 px"),
            "provider": "Sentinel-2 / High-Resolution Optical Earth Observation",
            "acquisition_date": before_date,
        }
        after_img = {
            "available": after_tile.get("success", False),
            "thumbnail_url": after_tile.get("url"),
            "image_path": after_tile.get("filepath"),
            "resolution": after_tile.get("resolution", "0.5m - 2.5m GSD"),
            "dimensions": after_tile.get("dimensions", "512 × 512 px"),
            "provider": "Sentinel-2 / High-Resolution Optical Earth Observation",
            "acquisition_date": after_date,
        }

        return jsonify({
            "success": True,
            "mode": "multitemporal",
            "place_name": place_name,
            "latitude": lat,
            "longitude": lon,
            "before": before_img,
            "after": after_img,
            "message": f"Retrieved high-resolution satellite imagery for {before_date} and {after_date}.",
        }), 200
    else:
        obs_date = (data.get("date") or "").strip() or None
        year = None
        if obs_date:
            try:
                year = int(obs_date.split("-")[0])
            except Exception:
                year = None

        tile = download_satellite_tile_image(lat, lon, zoom=16, year=year, prefix="sat_single")
        img_info = {
            "available": tile.get("success", False),
            "thumbnail_url": tile.get("url"),
            "image_path": tile.get("filepath"),
            "resolution": tile.get("resolution", "0.5m - 2.5m GSD"),
            "dimensions": tile.get("dimensions", "512 × 512 px"),
            "provider": "High-Resolution Earth Observation Imagery",
            "satellite": "Sentinel-2 / High-Resolution Optical Constellation",
            "acquisition_date": obs_date or "Current Acquisition",
        }
        return jsonify({
            "success": True,
            "mode": mode,
            "place_name": place_name,
            "latitude": lat,
            "longitude": lon,
            "image": img_info,
            "message": "Retrieved high-resolution satellite imagery.",
        }), 200



# ── single / optical-sar by coordinates ──────────────────────────────────────

@coordinates_bp.route("/coordinates", methods=["POST"])
@jwt_required()
def analyze_coordinates():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    mode = (data.get("mode") or "single").lower()
    if mode not in ("single", "optical_sar"):
        mode = "single"

    lat, lon, errors = _validate_coords(data.get("latitude"), data.get("longitude"))
    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    obs_date = (data.get("date") or "").strip() or None
    obs_time = (data.get("time") or "").strip() or None
    nl_query = (data.get("nl_query") or "").strip() or None

    # Reverse geocode
    place_name = reverse_geocode(lat, lon)

    # Fetch real satellite imagery tile
    imagery_info = fetch_satellite_imagery(lat, lon, date=obs_date, mode=mode)
    image1_path = imagery_info.get("image_path")

    analysis = Analysis(
        user_id=user_id,
        mode=mode,
        input_type="coordinates",
        latitude=lat,
        longitude=lon,
        place_name=place_name,
        before_date=obs_date,
        before_time=obs_time,
        nl_query=nl_query,
        status="pending",
    )
    db.session.add(analysis)
    db.session.flush()
    db.session.commit()

    try:
        analysis.status = "processing"
        db.session.commit()

        result = run_analysis_pipeline(
            mode=mode,
            image1_path=image1_path,
            latitude=lat,
            longitude=lon,
            place_name=place_name,
            obs_date=obs_date,
            imagery_info=imagery_info,
            nl_query=nl_query,
            analysis_id=analysis.id,
        )

        analysis.status = "completed"
        analysis.result_json = json.dumps(result)
        analysis.overall_confidence = result.get("overall_confidence")
        analysis.nl_answer = result.get("nl_answer")
        analysis.completed_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({"success": True, "analysis_id": analysis.id, "result": result}), 200

    except Exception as exc:
        analysis.status = "failed"
        analysis.error_message = str(exc)
        db.session.commit()
        current_app.logger.exception("Coordinate analysis failed for %s", analysis.id)
        return jsonify({"success": False, "error": "Analysis failed.", "detail": str(exc)}), 500


# ── multitemporal by coordinates (2 different years/dates) ───────────────────

@coordinates_bp.route("/coordinates/multitemporal", methods=["POST"])
@jwt_required()
def analyze_coordinates_multitemporal():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    lat, lon, errors = _validate_coords(data.get("latitude"), data.get("longitude"))
    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    before_date = (data.get("before_date") or "").strip() or "2020-01-01"
    before_time = (data.get("before_time") or "").strip() or None
    after_date = (data.get("after_date") or "").strip() or "2024-01-01"
    after_time = (data.get("after_time") or "").strip() or None
    nl_query = (data.get("nl_query") or "").strip() or None

    if not before_date:
        return jsonify({"success": False, "errors": {"before_date": "Before date is required."}}), 422
    if not after_date:
        return jsonify({"success": False, "errors": {"after_date": "After date is required."}}), 422

    place_name = reverse_geocode(lat, lon)

    # Fetch 2 observations for the 2 different years/dates
    before_imagery = fetch_satellite_imagery(lat, lon, date=before_date, mode="multitemporal_before")
    after_imagery = fetch_satellite_imagery(lat, lon, date=after_date, mode="multitemporal_after")

    image1_path = before_imagery.get("image_path")
    image2_path = after_imagery.get("image_path")

    analysis = Analysis(
        user_id=user_id,
        mode="multitemporal",
        input_type="coordinates",
        latitude=lat,
        longitude=lon,
        place_name=place_name,
        before_date=before_date,
        before_time=before_time,
        after_date=after_date,
        after_time=after_time,
        nl_query=nl_query,
        status="pending",
    )
    db.session.add(analysis)
    db.session.flush()
    db.session.commit()

    try:
        analysis.status = "processing"
        db.session.commit()

        result = run_analysis_pipeline(
            mode="multitemporal",
            image1_path=image1_path,
            image2_path=image2_path,
            latitude=lat,
            longitude=lon,
            place_name=place_name,
            before_date=before_date,
            after_date=after_date,
            imagery_info={"before": before_imagery, "after": after_imagery},
            nl_query=nl_query,
            analysis_id=analysis.id,
        )

        analysis.status = "completed"
        analysis.result_json = json.dumps(result)
        analysis.overall_confidence = result.get("overall_confidence")
        analysis.nl_answer = result.get("nl_answer")
        analysis.completed_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({"success": True, "analysis_id": analysis.id, "result": result}), 200

    except Exception as exc:
        analysis.status = "failed"
        analysis.error_message = str(exc)
        db.session.commit()
        current_app.logger.exception("Coordinate multitemporal analysis failed for %s", analysis.id)
        return jsonify({"success": False, "error": "Analysis failed.", "detail": str(exc)}), 500
