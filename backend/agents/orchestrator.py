"""
SATQUERY AI — Agentic Orchestration Layer
Selects and sequences agents based on analysis mode.
Modes: "single" | "optical_sar" | "multitemporal"
Input types: "image" | "coordinates"
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from agents import (
    preprocessing_agent,
    landcover_agent,
    building_agent,
    water_agent,
    agriculture_agent,
    change_detection_agent,
    evidence_agent,
    confidence_agent,
)
from data.bigearthnet.loader import get_bigearthnet_labels

logger = logging.getLogger(__name__)


def run_analysis_pipeline(
    mode: str = "single",
    image1_path: Optional[str] = None,
    image2_path: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    place_name: Optional[str] = None,
    obs_date: Optional[str] = None,
    before_date: Optional[str] = None,
    after_date: Optional[str] = None,
    imagery_info: Optional[dict] = None,
    nl_query: Optional[str] = None,
    analysis_id: Optional[str] = None,
    progress_callback=None,
) -> dict:
    """
    Master orchestrator. Returns a complete result dict.
    """
    logger.info("Orchestrator: starting pipeline mode=%s id=%s", mode, analysis_id)

    input_type = "image" if image1_path else "coordinates"
    started_at = datetime.now(timezone.utc).isoformat()

    # Determine upload folder for evidence
    try:
        from flask import current_app
        upload_folder = current_app.config.get("UPLOAD_FOLDER", "")
    except RuntimeError:
        upload_folder = os.path.join(os.path.dirname(__file__), "..", "uploads")

    # ── Stage 1: Input Validation ─────────────────────────────────────────
    stages = ["Input Validation"]
    validation = _validate_inputs(mode, image1_path, image2_path, latitude, longitude)
    if not validation["valid"]:
        return _error_result(validation["errors"], started_at, mode, analysis_id)

    # ── Stage 2: Preprocessing ─────────────────────────────────────────────
    stages.append("Image Preprocessing")
    pre1 = preprocessing_agent.run(image_path=image1_path, role="primary" if mode == "single" else "before/optical")
    pre2 = None
    if image2_path:
        pre2 = preprocessing_agent.run(image_path=image2_path, role="sar/after")

    # ── Stage 3: BigEarthNet labels (if dataset path configured) ──────────
    stages.append("Modality Identification")
    ben_labels = None
    if image1_path:
        try:
            ben_labels = get_bigearthnet_labels(image1_path)
        except Exception as e:
            logger.debug("BigEarthNet label lookup skipped: %s", e)

    # ── Stage 4: Land Cover ────────────────────────────────────────────────
    stages.append("Land Cover Analysis")
    landcover = landcover_agent.run(
        image_path=image1_path,
        pre_result=pre1,
        bigearthnet_labels=ben_labels,
    )

    # ── Stage 5: Building Detection ────────────────────────────────────────
    stages.append("Building Detection")
    buildings = building_agent.run(image_path=image1_path, pre_result=pre1)

    # ── Stage 6: Water Body Analysis ──────────────────────────────────────
    stages.append("Water Body Analysis")
    water = water_agent.run(image_path=image1_path, pre_result=pre1)

    # ── Stage 7: Agriculture Analysis ─────────────────────────────────────
    stages.append("Agriculture Analysis")
    agriculture = agriculture_agent.run(image_path=image1_path, pre_result=pre1)

    # ── Stage 8: Change Detection (multitemporal only) ─────────────────────
    stages.append("Change Detection")
    change = None
    if mode == "multitemporal":
        change = change_detection_agent.run(
            image1_path=image1_path,
            image2_path=image2_path,
            pre1=pre1,
            pre2=pre2,
        )

    # ── Stage 9: Visual Evidence ───────────────────────────────────────────
    stages.append("Generating Visual Evidence")
    evidence = evidence_agent.run(
        image1_path=image1_path,
        image2_path=image2_path,
        water_result=water,
        agriculture_result=agriculture,
        landcover_result=landcover,
        building_result=buildings,
        change_result=change,
        upload_folder=upload_folder,
    )

    # ── Stage 10: Confidence Estimation ───────────────────────────────────
    stages.append("Confidence Estimation")
    confidence_info = confidence_agent.run(
        pre_result=pre1,
        landcover_result=landcover,
        building_result=buildings,
        water_result=water,
        agriculture_result=agriculture,
        change_result=change,
        mode=mode,
        input_type=input_type,
    )

    # ── Stage 11: Natural Language Answer ─────────────────────────────────
    stages.append("Natural Language Processing")
    nl_answer = None
    if nl_query:
        result_so_far = {
            "landcover": landcover,
            "buildings": buildings,
            "water": water,
            "agriculture": agriculture,
            "change": change,
        }
        nl_answer = answer_natural_language_query(nl_query, result_so_far)

    # ── Stage 12: Evidence Validation & Report Preparation ────────────────
    stages.append("Evidence Validation")
    stages.append("Preparing Report")

    completed_at = datetime.now(timezone.utc).isoformat()

    # ── Assemble final result ──────────────────────────────────────────────
    result = {
        "analysis_id": analysis_id,
        "mode": mode,
        "input_type": input_type,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
            "place_name": place_name,
        },
        "dates": {
            "before": before_date,
            "after": after_date,
            "observation": obs_date,
        },
        "imagery_info": imagery_info or {},
        "data_source": _data_source_info(imagery_info),
        "model_info": {
            "dataset": "BigEarthNet (reference/training dataset)",
            "note": "Connect LANDCOVER_MODEL_PATH in .env to enable trained model inference.",
        },
        "stages_completed": stages,
        "started_at": started_at,
        "completed_at": completed_at,

        "preprocessing": {
            "image1": _safe_pre(pre1),
            "image2": _safe_pre(pre2),
        },
        "landcover": landcover,
        "buildings": buildings,
        "water": water,
        "agriculture": agriculture,
        "change_detection": change,
        "evidence": evidence,
        "confidence": confidence_info,
        "overall_confidence": confidence_info.get("overall_confidence"),
        "nl_query": nl_query,
        "nl_answer": nl_answer,
        "limitations": _build_limitations(
            pre1, landcover, buildings, water, agriculture, change, input_type
        ),
    }

    # ── Evidence validation (runs after result is assembled) ──────────────
    try:
        from services.evidence_validator import EvidenceValidator
        result = EvidenceValidator().validate_result(result)
    except Exception as _val_err:
        logger.warning("Evidence validation failed (non-fatal): %s", _val_err)

    logger.info(
        "Orchestrator: pipeline complete id=%s confidence=%.1f",
        analysis_id,
        result["overall_confidence"] or 0,
    )
    return result


# ── NL Query ──────────────────────────────────────────────────────────────────

def answer_natural_language_query(query: str, result: dict) -> str:
    """
    Rule-based NL query responder.
    Extends with an LLM call when an API key is configured.
    """
    q = query.lower().strip()
    parts = []

    lc = result.get("landcover", {})
    water = result.get("water", {})
    agri = result.get("agriculture", {})
    bld = result.get("buildings", {})
    chg = result.get("change", result.get("change_detection", {}))

    # ── Land cover ────────────────────────────────────────────────────────
    if any(kw in q for kw in ["land cover", "land use", "cover", "classification"]):
        classes = lc.get("classes", [])
        if classes:
            top = sorted(classes, key=lambda c: c.get("percentage") or 0, reverse=True)
            desc = ", ".join(
                f"{c['label']} ({c.get('percentage') or 'N/A'}%)"
                for c in top[:3]
            )
            parts.append(f"The dominant land cover classes detected are: {desc}.")
        else:
            parts.append("Land cover classification data is unavailable for this analysis.")

    # ── Water ─────────────────────────────────────────────────────────────
    if any(kw in q for kw in ["water", "river", "lake", "flood", "ocean", "sea"]):
        pct = water.get("water_coverage_pct")
        count = water.get("water_body_count")
        locs = water.get("locations", [])
        if pct is not None:
            area_str = (
                f" (approximately {water['water_area_km2']} km²)"
                if water.get("water_area_km2") else ""
            )
            count_str = f" {count} distinct water body/bodies detected." if count else ""
            loc_str = f" Located in: {', '.join(locs)}." if locs else ""
            parts.append(
                f"Water bodies cover approximately {pct:.1f}% of the analysed area{area_str}.{count_str}{loc_str}"
            )
        else:
            parts.append("Water body data is unavailable for this analysis.")

    # ── Agriculture ───────────────────────────────────────────────────────
    if any(kw in q for kw in ["agriculture", "crop", "farm", "field", "vegetation"]):
        a_pct = agri.get("agriculture_pct")
        a_area = agri.get("agriculture_area_km2")
        if a_pct is not None:
            area_str = f" (approximately {a_area} km²)" if a_area else ""
            regions = agri.get("regions", [])
            region_str = ""
            if regions:
                dirs = [r["direction"] for r in regions]
                region_str = f" Concentrated in the {', '.join(dirs)} region(s)."
            parts.append(
                f"Agricultural/cropland covers approximately {a_pct:.1f}% of the image{area_str}.{region_str}"
            )
        else:
            parts.append("Agricultural area data is unavailable for this analysis.")

    # ── Buildings ─────────────────────────────────────────────────────────
    if any(kw in q for kw in ["building", "structure", "urban", "construction", "house"]):
        count = bld.get("building_count")
        lim = bld.get("limitation")
        if count is not None:
            parts.append(f"Approximately {count} building(s) detected in the analysed area.")
        elif lim:
            parts.append(f"Buildings: {lim}")
        else:
            parts.append("Building count is not available for this analysis.")

    # ── Change detection ──────────────────────────────────────────────────
    if any(kw in q for kw in ["change", "differ", "before", "after", "compare"]):
        if chg:
            if chg.get("changes_detected"):
                pct = chg.get("overall_change_pct", 0)
                summary = chg.get("change_summary", [])
                types = [s["type"] for s in summary]
                parts.append(
                    f"Changes detected affecting approximately {pct:.1f}% of the analysed area. "
                    f"Types: {'; '.join(types)}."
                )
            else:
                parts.append("No significant change reliably detected between the two images.")
        else:
            parts.append("Change detection is only available in Multitemporal mode.")

    # ── Direction queries ─────────────────────────────────────────────────
    for direction in ["north", "south", "east", "west", "north-east", "north-west", "south-east", "south-west"]:
        if direction in q:
            findings = []
            for lc_class in lc.get("classes", []):
                if lc_class.get("direction", "").lower() == direction:
                    findings.append(f"{lc_class['label']} ({lc_class.get('percentage', '?')}%)")
            if water.get("locations"):
                for loc in water["locations"]:
                    if loc.lower() == direction:
                        findings.append("water body")
            if findings:
                parts.append(
                    f"In the {direction.title()} portion of the analysed area: {', '.join(findings)}."
                )
            else:
                parts.append(
                    f"No specific features reliably identified in the {direction.title()} region "
                    "from the available data."
                )

    if not parts:
        # Generic fallback
        conf = result.get("confidence", {})
        oc = conf.get("overall_confidence") if isinstance(conf, dict) else None
        conf_str = f" Overall confidence: {oc:.0f}/100." if oc else ""
        parts.append(
            f"The analysis has processed the available satellite data.{conf_str} "
            "Please ask a more specific question about land cover, water, agriculture, "
            "buildings, or changes detected in this image."
        )

    return " ".join(parts)


# ── private helpers ───────────────────────────────────────────────────────────

def _validate_inputs(mode, image1_path, image2_path, lat, lon):
    errors = []
    if not image1_path and (lat is None or lon is None):
        errors.append("Either an image or valid coordinates (latitude/longitude) must be supplied.")
    if mode == "multitemporal" and image1_path and not image2_path:
        errors.append("Multitemporal mode requires both a before and after image.")
    return {"valid": len(errors) == 0, "errors": errors}


def _safe_pre(pre: Optional[dict]) -> dict:
    if not pre:
        return {}
    return {k: v for k, v in pre.items() if k != "_array"}


def _data_source_info(imagery_info: Optional[dict]) -> dict:
    if not imagery_info:
        return {
            "provider": "User-uploaded image",
            "satellite": "Unknown (no metadata)",
            "note": "Connect SATELLITE_PROVIDER in .env for automatic imagery retrieval.",
        }
    provider = imagery_info.get("provider", "Unknown")
    return {
        "provider": provider,
        "satellite": imagery_info.get("satellite", "Unknown"),
        "acquisition_date": imagery_info.get("date"),
        "resolution": imagery_info.get("resolution"),
    }


def _build_limitations(pre1, lc, bld, water, agri, chg, input_type) -> list:
    lims = []
    if not (pre1 and pre1.get("has_georeference")):
        lims.append("Image lacks georeferencing: real-world area calculations are unavailable.")
    if lc and lc.get("method") in ("spectral_heuristic", "unavailable"):
        lims.append("Land cover classification uses heuristics. Accuracy improves with a trained model.")
    if bld and bld.get("limitation"):
        lims.append(bld["limitation"])
    if water and water.get("method") == "brightness_heuristic":
        lims.append("Water detection uses brightness heuristics; NIR band improves accuracy.")
    if agri and agri.get("method") == "greenness_heuristic":
        lims.append("Agriculture detection uses greenness proxy; true NDVI requires NIR + Red bands.")
    if input_type == "coordinates" and not chg:
        lims.append(
            "Coordinate-based analysis without a connected satellite imagery API cannot "
            "retrieve actual imagery. Results reflect the configured data source only."
        )
    return lims


def _error_result(errors, started_at, mode, analysis_id) -> dict:
    return {
        "analysis_id": analysis_id,
        "mode": mode,
        "success": False,
        "errors": errors,
        "started_at": started_at,
        "overall_confidence": 0.0,
    }
