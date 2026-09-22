"""
SATQUERY AI — Water Body Detection Agent
Detects water bodies and estimates water extent from satellite imagery.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run(image_path: Optional[str] = None, pre_result: Optional[dict] = None) -> dict:
    """
    Returns:
        success             : bool
        water_body_count    : int | None
        water_coverage_pct  : float | None
        water_area_km2      : float | None
        locations           : list[str]  — cardinal directions
        confidence          : float
        method              : str
        notes               : list[str]
        water_level_note    : str
    """
    result = {
        "success": False,
        "water_body_count": None,
        "water_coverage_pct": None,
        "water_area_km2": None,
        "locations": [],
        "confidence": 0.0,
        "method": "unavailable",
        "notes": [],
        "water_level_note": (
            "Absolute water depth/level cannot be determined from standard optical "
            "satellite imagery. Water extent percentage is available where detectable. "
            "Absolute level requires validated elevation or hydrological data."
        ),
    }

    if not image_path or not os.path.exists(image_path):
        result["method"] = "coordinate_only"
        result["notes"].append(
            "Water body analysis requires a satellite image or a connected imagery API."
        )
        result["success"] = True
        return result

    try:
        water_data = _detect_water(image_path, pre_result)
        result.update(water_data)
        result["success"] = True
    except Exception as e:
        result["notes"].append(f"Water detection failed: {e}")
        result["success"] = False

    return result


def _detect_water(image_path: str, pre_result: Optional[dict]) -> dict:
    """
    NDWI-inspired water detection using brightness/spectral heuristics.
    When actual multispectral bands (green, NIR) are available,
    replace this with: NDWI = (Green - NIR) / (Green + NIR), threshold > 0.
    """
    import numpy as np

    try:
        from PIL import Image as PILImage
        img = PILImage.open(image_path).convert("L")
        arr = np.array(img, dtype="float32") / 255.0
    except Exception as e:
        raise RuntimeError(f"Could not load image: {e}")

    height, width = arr.shape
    half_h, half_w = height // 2, width // 2
    total_pixels = arr.size

    # Dark pixels proxy for water (very approximate without NIR band)
    water_mask = arr < 0.18
    water_pct = float(water_mask.sum() / total_pixels) * 100

    # Pixel size → area
    water_area_km2 = None
    if pre_result and pre_result.get("pixel_size_m"):
        px = pre_result["pixel_size_m"]
        water_area_km2 = round((px * px * water_mask.sum()) / 1_000_000, 3)

    # Estimate locations (connected regions approximation via quadrant)
    locations = _quadrant_locations(water_mask, half_h, half_w)

    # Very rough body count via labelling
    water_body_count = None
    try:
        from scipy import ndimage
        labeled, count = ndimage.label(water_mask)
        # Filter tiny blobs (< 0.1% of image)
        min_size = int(total_pixels * 0.001)
        sizes = ndimage.sum(water_mask, labeled, range(1, count + 1))
        significant = sum(1 for s in sizes if s >= min_size)
        water_body_count = significant if significant > 0 else None
    except ImportError:
        pass  # scipy not available

    confidence = 55.0 if water_pct > 2 else 30.0

    notes = [
        "Water detection based on brightness heuristics (single-band). "
        "For accurate NDWI-based detection, supply a multispectral image with NIR band."
    ]
    if not water_area_km2:
        notes.append("Area not calculable: image lacks georeferencing metadata.")

    return {
        "water_body_count": water_body_count,
        "water_coverage_pct": round(water_pct, 2),
        "water_area_km2": water_area_km2,
        "locations": locations,
        "confidence": confidence,
        "method": "brightness_heuristic",
        "notes": notes,
    }


def _quadrant_locations(mask, half_h: int, half_w: int) -> list:
    """Return list of cardinal direction strings for mask's non-zero quadrants."""
    import numpy as np
    if mask.sum() == 0:
        return []

    quad_map = {
        "North-West": mask[:half_h, :half_w],
        "North-East": mask[:half_h, half_w:],
        "South-West": mask[half_h:, :half_w],
        "South-East": mask[half_h:, half_w:],
    }
    threshold = mask.sum() * 0.05  # quadrant must hold ≥5% of water pixels
    return [direction for direction, q in quad_map.items() if q.sum() >= threshold]
