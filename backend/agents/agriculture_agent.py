"""
SATQUERY AI — Agriculture Detection Agent
Estimates agricultural/cropland extent from satellite imagery.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run(image_path: Optional[str] = None, pre_result: Optional[dict] = None) -> dict:
    """
    Returns:
        success             : bool
        agriculture_pct     : float | None
        agriculture_area_km2: float | None
        regions             : list[dict]  — {direction, area_km2}
        confidence          : float
        method              : str
        notes               : list[str]
    """
    result = {
        "success": False,
        "agriculture_pct": None,
        "agriculture_area_km2": None,
        "regions": [],
        "confidence": 0.0,
        "method": "unavailable",
        "notes": [],
    }

    if not image_path or not os.path.exists(image_path):
        result["method"] = "coordinate_only"
        result["notes"].append(
            "Agriculture analysis requires a satellite image or a connected imagery API."
        )
        result["success"] = True
        return result

    try:
        agri_data = _detect_agriculture(image_path, pre_result)
        result.update(agri_data)
        result["success"] = True
    except Exception as e:
        result["notes"].append(f"Agriculture detection failed: {e}")
        result["success"] = False

    return result


def _detect_agriculture(image_path: str, pre_result: Optional[dict]) -> dict:
    """
    NDVI-inspired approach using brightness proxies.
    Real NDVI = (NIR - Red) / (NIR + Red) — requires multispectral image.
    """
    import numpy as np

    try:
        from PIL import Image as PILImage
        img = PILImage.open(image_path)
        # Use green channel as proxy for vegetation if RGB available
        if img.mode in ("RGB", "RGBA"):
            arr_g = np.array(img.getchannel("G"), dtype="float32") / 255.0
            arr_r = np.array(img.getchannel("R"), dtype="float32") / 255.0
            # Simple greenness index
            denom = arr_g + arr_r
            with np.errstate(divide='ignore', invalid='ignore'):
                gi = np.where(denom > 0, (arr_g - arr_r) / denom, 0)
            agri_mask = gi > 0.05
        else:
            arr = np.array(img.convert("L"), dtype="float32") / 255.0
            # Mid-brightness band approximation
            agri_mask = (arr >= 0.30) & (arr < 0.55)
    except Exception as e:
        raise RuntimeError(f"Could not load image: {e}")

    height, width = agri_mask.shape
    half_h, half_w = height // 2, width // 2
    total_pixels = agri_mask.size

    agri_pct = round(float(agri_mask.sum() / total_pixels) * 100, 2)

    agri_area_km2 = None
    if pre_result and pre_result.get("pixel_size_m"):
        px = pre_result["pixel_size_m"]
        agri_area_km2 = round((px * px * agri_mask.sum()) / 1_000_000, 3)

    # Regions by quadrant
    regions = _region_breakdown(agri_mask, half_h, half_w, pre_result)
    confidence = 50.0 if agri_pct > 5 else 30.0

    notes = [
        "Agriculture estimation uses greenness/brightness heuristics. "
        "For accurate NDVI-based cropland detection, supply a multispectral image (NIR + Red bands)."
    ]
    if not agri_area_km2:
        notes.append("Area not calculable: image lacks georeferencing metadata.")

    return {
        "agriculture_pct": agri_pct,
        "agriculture_area_km2": agri_area_km2,
        "regions": regions,
        "confidence": confidence,
        "method": "greenness_heuristic",
        "notes": notes,
    }


def _region_breakdown(mask, half_h: int, half_w: int, pre_result: Optional[dict]) -> list:
    """Break down agricultural areas by quadrant direction."""
    import numpy as np

    total = mask.sum()
    if total == 0:
        return []

    quadrants = {
        "North-West": mask[:half_h, :half_w],
        "North-East": mask[:half_h, half_w:],
        "South-West": mask[half_h:, :half_w],
        "South-East": mask[half_h:, half_w:],
    }

    regions = []
    for direction, q in quadrants.items():
        q_sum = q.sum()
        if q_sum / total < 0.05:
            continue
        area_km2 = None
        if pre_result and pre_result.get("pixel_size_m"):
            px = pre_result["pixel_size_m"]
            area_km2 = round((px * px * q_sum) / 1_000_000, 3)
        regions.append({"direction": direction, "area_km2": area_km2, "pixel_count": int(q_sum)})

    return regions
