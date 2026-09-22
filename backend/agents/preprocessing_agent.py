"""
SATQUERY AI — Image Preprocessing Agent
Loads, validates and normalises a satellite image for downstream agents.
Returns image metadata and a normalised numpy array (if available).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def run(image_path: Optional[str] = None, role: str = "primary") -> dict:
    """
    Preprocess a satellite image file.

    Returns a dict with:
        success         : bool
        width           : int | None
        height          : int | None
        channels        : int | None
        dtype           : str | None
        has_georeference: bool
        crs             : str | None
        pixel_size_m    : float | None   — ground sampling distance if available
        cloud_coverage  : float | None   — 0-100 if detectable
        quality_score   : float          — 0-100 heuristic image quality
        notes           : list[str]
        array           : not serialised — held in memory by orchestrator
    """
    result = {
        "success": False,
        "role": role,
        "width": None,
        "height": None,
        "channels": None,
        "dtype": None,
        "has_georeference": False,
        "crs": None,
        "pixel_size_m": None,
        "cloud_coverage": None,
        "quality_score": 50.0,
        "notes": [],
        "_array": None,  # numpy array, not returned in JSON
    }

    if not image_path:
        result["notes"].append("No image path supplied — coordinate-only analysis.")
        result["success"] = True
        return result

    if not os.path.exists(image_path):
        result["notes"].append(f"Image file not found: {image_path}")
        return result

    # ── Try rasterio (GeoTIFF / georeferenced) ────────────────────────────
    try:
        import rasterio
        with rasterio.open(image_path) as src:
            result["width"] = src.width
            result["height"] = src.height
            result["channels"] = src.count
            result["dtype"] = str(src.dtypes[0])
            if src.crs:
                result["has_georeference"] = True
                result["crs"] = str(src.crs)
            transform = src.transform
            if transform and transform.a != 0:
                result["pixel_size_m"] = abs(transform.a)
            # Read first band for quality heuristics
            band = src.read(1).astype("float32")
            result["_array"] = band
            result["quality_score"] = _quality_score(band, result["channels"])
            result["notes"].append("Image loaded via rasterio (GeoTIFF).")
            result["success"] = True
            return result
    except ImportError:
        result["notes"].append("rasterio not installed — falling back to Pillow.")
    except Exception as e:
        result["notes"].append(f"rasterio failed ({e}) — falling back to Pillow.")

    # ── Fallback: Pillow ──────────────────────────────────────────────────
    try:
        from PIL import Image as PILImage
        import numpy as np
        with PILImage.open(image_path) as img:
            result["width"], result["height"] = img.size
            result["channels"] = len(img.getbands())
            arr = np.array(img.convert("L"), dtype="float32")
            result["_array"] = arr
            result["dtype"] = str(arr.dtype)
            result["quality_score"] = _quality_score(arr, result["channels"])
            result["notes"].append("Image loaded via Pillow.")
            result["success"] = True
            return result
    except ImportError:
        result["notes"].append("Pillow not installed. Install Pillow or rasterio.")
    except Exception as e:
        result["notes"].append(f"Pillow failed: {e}")

    return result


def _quality_score(band, channels: int) -> float:
    """Heuristic quality score based on dynamic range and contrast."""
    try:
        import numpy as np
        p_low = float(np.percentile(band, 2))
        p_high = float(np.percentile(band, 98))
        dynamic_range = p_high - p_low
        # Normalise to 0-100
        if dynamic_range < 1:
            return 20.0   # near-flat image — likely blank or corrupted
        score = min(100.0, (dynamic_range / 255.0) * 100.0)
        # Penalise single channel
        if channels and channels == 1:
            score *= 0.85
        return round(score, 1)
    except Exception:
        return 50.0
