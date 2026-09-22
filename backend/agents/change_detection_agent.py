"""
SATQUERY AI — Change Detection Agent
Compares two satellite images (before/after) to identify changes.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CHANGE_TYPES = [
    "New Construction",
    "Removed Structures",
    "Vegetation Gain",
    "Vegetation Loss",
    "Water Expansion",
    "Water Reduction",
    "Agricultural Change",
    "Bare Land Change",
    "Other",
]


def run(
    image1_path: Optional[str] = None,
    image2_path: Optional[str] = None,
    pre1: Optional[dict] = None,
    pre2: Optional[dict] = None,
) -> dict:
    """
    Returns:
        success             : bool
        changes_detected    : bool
        change_summary      : list[dict]  — {type, area_km2, direction, before, after, confidence}
        change_map_path     : str | None  — saved change-map image path
        overall_change_pct  : float | None
        confidence          : float
        method              : str
        notes               : list[str]
    """
    result = {
        "success": False,
        "changes_detected": False,
        "change_summary": [],
        "change_map_path": None,
        "overall_change_pct": None,
        "confidence": 0.0,
        "method": "unavailable",
        "notes": [],
    }

    missing = []
    if not image1_path or not os.path.exists(image1_path):
        missing.append("before image")
    if not image2_path or not os.path.exists(image2_path):
        missing.append("after image")

    if missing:
        result["notes"].append(
            f"Change detection requires both images. Missing: {', '.join(missing)}."
        )
        result["method"] = "insufficient_data"
        result["success"] = True
        return result

    try:
        change_data = _compute_changes(image1_path, image2_path, pre1, pre2)
        result.update(change_data)
        result["success"] = True
    except Exception as e:
        result["notes"].append(f"Change detection failed: {e}")
        result["success"] = False

    return result


def _compute_changes(
    path1: str, path2: str,
    pre1: Optional[dict], pre2: Optional[dict],
) -> dict:
    """
    Image differencing approach:
    1. Load both images as grayscale arrays.
    2. Resize to common size if necessary.
    3. Compute absolute difference.
    4. Threshold to binary change mask.
    5. Classify change regions by brightness delta direction.
    """
    import numpy as np
    from PIL import Image as PILImage

    try:
        img1 = PILImage.open(path1).convert("L")
        img2 = PILImage.open(path2).convert("L")
    except Exception as e:
        raise RuntimeError(f"Could not load images: {e}")

    # Align sizes
    if img1.size != img2.size:
        target = (min(img1.width, img2.width), min(img1.height, img2.height))
        img1 = img1.resize(target, PILImage.LANCZOS)
        img2 = img2.resize(target, PILImage.LANCZOS)

    arr1 = np.array(img1, dtype="float32") / 255.0
    arr2 = np.array(img2, dtype="float32") / 255.0

    diff = arr2 - arr1             # positive = brighter (new construction / bare land)
    abs_diff = np.abs(diff)

    height, width = arr1.shape
    total_pixels = arr1.size
    half_h, half_w = height // 2, width // 2

    # Threshold: pixels that changed by more than 15% brightness
    THRESHOLD = 0.15
    change_mask = abs_diff > THRESHOLD
    overall_change_pct = round(float(change_mask.sum() / total_pixels) * 100, 2)

    if overall_change_pct < 1.0:
        return {
            "changes_detected": False,
            "change_summary": [],
            "overall_change_pct": overall_change_pct,
            "confidence": 60.0,
            "method": "image_differencing",
            "notes": ["No significant change reliably detected between the two images."],
        }

    # Classify changes
    gain_mask = diff > THRESHOLD     # got brighter
    loss_mask = diff < -THRESHOLD    # got darker

    pixel_size = None
    if pre1 and pre1.get("pixel_size_m"):
        pixel_size = pre1["pixel_size_m"]

    def km2(mask):
        if pixel_size:
            return round((pixel_size * pixel_size * mask.sum()) / 1_000_000, 3)
        return None

    def direction(mask):
        if mask.sum() == 0:
            return "N/A"
        ys, xs = np.where(mask)
        cy, cx = ys.mean(), xs.mean()
        ns = "North" if cy < half_h else "South"
        ew = "East" if cx > half_w else "West"
        return f"{ns}-{ew}"

    change_summary = []

    # Bright gain → new construction / bare land exposure
    if gain_mask.sum() / total_pixels > 0.005:
        change_summary.append({
            "type": "Brightness Gain (possible construction / bare land exposure)",
            "area_km2": km2(gain_mask),
            "direction": direction(gain_mask),
            "before": "darker surface",
            "after": "brighter surface",
            "confidence": 52.0,
        })

    # Dark gain → vegetation growth / water expansion
    if loss_mask.sum() / total_pixels > 0.005:
        change_summary.append({
            "type": "Brightness Loss (possible vegetation growth / water expansion)",
            "area_km2": km2(loss_mask),
            "direction": direction(loss_mask),
            "before": "brighter surface",
            "after": "darker surface",
            "confidence": 52.0,
        })

    notes = [
        "Change detection uses image-differencing on brightness channel. "
        "For accurate semantic change detection (e.g. building vs water), "
        "supply multispectral imagery and connect a trained change-detection model.",
    ]
    if img1.size != img2.size:
        notes.append("Images were resized to a common resolution for comparison.")
    if not pixel_size:
        notes.append("Area values not calculable: georeferencing metadata unavailable.")

    return {
        "changes_detected": True,
        "change_summary": change_summary,
        "overall_change_pct": overall_change_pct,
        "confidence": 55.0,
        "method": "image_differencing",
        "notes": notes,
    }
