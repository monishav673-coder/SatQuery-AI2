"""
SATQUERY AI — Building Detection Agent
Detects built-up structures in satellite imagery.
Returns counts and bounding boxes when a detection model is available.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run(image_path: Optional[str] = None, pre_result: Optional[dict] = None) -> dict:
    """
    Returns:
        success         : bool
        building_count  : int | None
        clusters        : list[dict]  — {location_direction, count, confidence}
        confidence      : float
        method          : str
        notes           : list[str]
        bounding_boxes  : list | None  — pixel coords when model available
        limitation      : str | None
    """
    result = {
        "success": False,
        "building_count": None,
        "clusters": [],
        "confidence": 0.0,
        "method": "unavailable",
        "notes": [],
        "bounding_boxes": None,
        "limitation": None,
    }

    if not image_path or not os.path.exists(image_path):
        result["method"] = "coordinate_only"
        result["limitation"] = (
            "Building detection requires a satellite image. "
            "Connect a satellite imagery API to enable coordinate-based detection."
        )
        result["success"] = True
        return result

    # ── Check resolution ──────────────────────────────────────────────────
    if pre_result:
        px_m = pre_result.get("pixel_size_m")
        if px_m and px_m > 15:
            result["limitation"] = (
                f"Image resolution ({px_m:.0f} m/pixel) is too coarse for reliable "
                "individual building detection. Results not reported."
            )
            result["method"] = "resolution_insufficient"
            result["confidence"] = 0.0
            result["success"] = True
            return result

    # ── Try detection model (placeholder) ────────────────────────────────
    try:
        detected = _detect_buildings(image_path, pre_result)
        result.update(detected)
        result["success"] = True
        return result
    except NotImplementedError:
        result["notes"].append(
            "No building detection model is configured. "
            "To enable: implement _detect_buildings() with a trained model (e.g. "
            "Faster R-CNN, YOLOv8, or a segmentation model trained on SpaceNet/INRIA)."
        )
        result["method"] = "model_not_configured"
        result["limitation"] = (
            "Building detection model not configured. "
            "A trained detection model is required for reliable building counts."
        )
        result["confidence"] = 0.0
        result["success"] = True
        return result
    except Exception as e:
        result["notes"].append(f"Building detection failed: {e}")
        result["success"] = False
        return result


def _detect_buildings(image_path: str, pre_result: Optional[dict]) -> dict:
    """
    Placeholder — implement with your preferred detection framework.
    Raise NotImplementedError until a real model is wired in.
    """
    raise NotImplementedError("Building detection model not configured.")
