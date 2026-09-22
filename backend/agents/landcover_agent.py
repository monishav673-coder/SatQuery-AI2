"""
SATQUERY AI — Land Cover Analysis Agent
Analyses pixel distribution to estimate land-cover classes.
Uses a trained model when available; falls back to spectral heuristics.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# BigEarthNet-aligned land-cover classes
LAND_COVER_CLASSES = [
    "Water",
    "Agriculture / Cropland",
    "Forest / Vegetation",
    "Built-up / Urban",
    "Bare Land",
    "Roads / Infrastructure",
    "Other",
]


def run(
    image_path: Optional[str] = None,
    pre_result: Optional[dict] = None,
    bigearthnet_labels: Optional[list] = None,
) -> dict:
    """
    Returns land-cover classification results.

    Keys returned:
        success      : bool
        classes      : list[dict]  — {label, percentage, area_km2, confidence, direction}
        method       : str         — "model" | "spectral_heuristic" | "coordinate_only"
        model_name   : str | None
        notes        : list[str]
        confidence   : float       — overall confidence for this agent (0-100)
    """
    result = {
        "success": False,
        "classes": [],
        "method": "unavailable",
        "model_name": None,
        "notes": [],
        "confidence": 0.0,
    }

    # ── If no image, return coordinate-only placeholder ───────────────────
    if not image_path or not os.path.exists(image_path):
        result["method"] = "coordinate_only"
        result["notes"].append(
            "No image available. Land-cover estimation requires a satellite image or "
            "a connected satellite imagery API. Area values cannot be calculated."
        )
        result["success"] = True
        result["confidence"] = 0.0
        return result

    # ── Try trained model ──────────────────────────────────────────────────
    model_path = ""
    try:
        from flask import current_app
        model_path = current_app.config.get("LANDCOVER_MODEL_PATH", "")
    except RuntimeError:
        model_path = os.environ.get("LANDCOVER_MODEL_PATH", "")
    if model_path and os.path.exists(model_path):
        try:
            model_result = _run_model(image_path, model_path, pre_result)
            result.update(model_result)
            result["success"] = True
            result["method"] = "model"
            return result
        except Exception as e:
            result["notes"].append(f"Model inference failed ({e}). Falling back to spectral heuristic.")

    # ── BigEarthNet labels (if passed from data module) ───────────────────
    if bigearthnet_labels:
        result["method"] = "bigearthnet_labels"
        result["classes"] = _labels_to_classes(bigearthnet_labels)
        result["confidence"] = 72.0
        result["notes"].append("Classification derived from BigEarthNet reference labels.")
        result["success"] = True
        return result

    # ── Spectral heuristic fallback ────────────────────────────────────────
    try:
        spectral = _spectral_heuristic(image_path, pre_result)
        result.update(spectral)
        result["method"] = "spectral_heuristic"
        result["success"] = True
        result["notes"].append(
            "Classification derived from pixel brightness/spectral heuristics. "
            "For accurate results, connect a trained land-cover model."
        )
    except Exception as e:
        result["notes"].append(f"Spectral heuristic failed: {e}")

    return result


# ── helpers ───────────────────────────────────────────────────────────────────

def _run_model(image_path: str, model_path: str, pre_result: dict) -> dict:
    """Placeholder for real model inference. Extend with your framework."""
    # TODO: load model with torch/tensorflow/onnxruntime and run inference
    raise NotImplementedError("Model inference not yet wired — set LANDCOVER_MODEL_PATH and implement _run_model.")


def _spectral_heuristic(image_path: str, pre_result: Optional[dict]) -> dict:
    """
    Very simple brightness-based heuristic — intended as a structural
    placeholder that produces honest, low-confidence estimates.
    Real accuracy requires a proper trained model.
    """
    import numpy as np

    classes = []
    confidence = 45.0   # low — this is just a heuristic

    try:
        # Try to load as grayscale
        try:
            from PIL import Image as PILImage
            img = PILImage.open(image_path).convert("L")
            arr = np.array(img, dtype="float32") / 255.0
        except Exception:
            arr = None

        if arr is None:
            raise ValueError("Could not load image array.")

        total_pixels = arr.size
        width = arr.shape[1]
        height = arr.shape[0]
        half_w = width // 2
        half_h = height // 2

        # Brightness thresholds (very approximate)
        dark_mask = arr < 0.15         # water / shadow
        medium_dark = (arr >= 0.15) & (arr < 0.35)   # vegetation
        medium = (arr >= 0.35) & (arr < 0.55)         # agriculture / mixed
        bright_medium = (arr >= 0.55) & (arr < 0.75)  # built-up
        bright = arr >= 0.75                           # bare land / bright urban

        def pct(mask):
            return round(float(mask.sum() / total_pixels) * 100, 1)

        def quad_direction(mask):
            """Return dominant quadrant direction."""
            if mask.sum() == 0:
                return "N/A"
            ys, xs = np.where(mask)
            mean_x = xs.mean()
            mean_y = ys.mean()
            north = mean_y < half_h
            east = mean_x > half_w
            if north and east:
                return "North-East"
            if north and not east:
                return "North-West"
            if not north and east:
                return "South-East"
            return "South-West"

        area_note = "Accurate area requires georeferencing metadata."
        if pre_result and pre_result.get("pixel_size_m") and pre_result.get("width") and pre_result.get("height"):
            px = pre_result["pixel_size_m"]
            total_area_km2 = (px * px * total_pixels) / 1_000_000
        else:
            total_area_km2 = None

        def area_str(pct_val):
            if total_area_km2:
                return round(total_area_km2 * pct_val / 100, 2)
            return None

        classes = [
            {
                "label": "Water",
                "percentage": pct(dark_mask),
                "area_km2": area_str(pct(dark_mask)),
                "confidence": 50.0,
                "direction": quad_direction(dark_mask),
            },
            {
                "label": "Forest / Vegetation",
                "percentage": pct(medium_dark),
                "area_km2": area_str(pct(medium_dark)),
                "confidence": 45.0,
                "direction": quad_direction(medium_dark),
            },
            {
                "label": "Agriculture / Cropland",
                "percentage": pct(medium),
                "area_km2": area_str(pct(medium)),
                "confidence": 40.0,
                "direction": quad_direction(medium),
            },
            {
                "label": "Built-up / Urban",
                "percentage": pct(bright_medium),
                "area_km2": area_str(pct(bright_medium)),
                "confidence": 42.0,
                "direction": quad_direction(bright_medium),
            },
            {
                "label": "Bare Land",
                "percentage": pct(bright),
                "area_km2": area_str(pct(bright)),
                "confidence": 38.0,
                "direction": quad_direction(bright),
            },
        ]

        if not total_area_km2:
            for c in classes:
                c["area_note"] = area_note

    except Exception as e:
        classes = []
        confidence = 0.0
        raise

    return {"classes": classes, "confidence": confidence}


def _labels_to_classes(labels: list) -> list:
    """Convert BigEarthNet multi-label list to class dicts."""
    # BigEarthNet labels are not percentages; we represent them as detected/not
    result = []
    for lbl in labels:
        result.append({
            "label": lbl,
            "percentage": None,
            "area_km2": None,
            "confidence": 75.0,
            "direction": "N/A",
            "note": "Derived from BigEarthNet reference labels.",
        })
    return result
