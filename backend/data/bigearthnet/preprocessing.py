"""
SATQUERY AI — BigEarthNet Preprocessing Utilities
Handles Sentinel-2 band loading, normalisation and patch preparation
compatible with BigEarthNet's data format.

BigEarthNet patches are stored as GeoTIFF files per band:
  <patch_name>/<patch_name>_B01.tif  (60m)
  <patch_name>/<patch_name>_B02.tif  (10m)
  ...
  <patch_name>/<patch_name>_B8A.tif  (20m)
  <patch_name>/<patch_name>_B09.tif  (60m)
  <patch_name>/<patch_name>_B11.tif  (20m)
  <patch_name>/<patch_name>_B12.tif  (20m)

Reference: https://bigearth.net/
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Sentinel-2 band names and their spatial resolutions in BigEarthNet
BAND_INFO = {
    "B01": {"res_m": 60,  "wavelength": "Coastal aerosol"},
    "B02": {"res_m": 10,  "wavelength": "Blue"},
    "B03": {"res_m": 10,  "wavelength": "Green"},
    "B04": {"res_m": 10,  "wavelength": "Red"},
    "B05": {"res_m": 20,  "wavelength": "Red edge 1"},
    "B06": {"res_m": 20,  "wavelength": "Red edge 2"},
    "B07": {"res_m": 20,  "wavelength": "Red edge 3"},
    "B08": {"res_m": 10,  "wavelength": "NIR"},
    "B8A": {"res_m": 20,  "wavelength": "Narrow NIR"},
    "B09": {"res_m": 60,  "wavelength": "Water vapour"},
    "B11": {"res_m": 20,  "wavelength": "SWIR 1"},
    "B12": {"res_m": 20,  "wavelength": "SWIR 2"},
}

# Typical BigEarthNet normalisation statistics (approximate per-band mean/std)
# These are representative values; replace with dataset-computed stats for best results.
BEN_NORM_STATS = {
    "B01": {"mean": 340.0,  "std": 554.0},
    "B02": {"mean": 429.0,  "std": 572.0},
    "B03": {"mean": 614.0,  "std": 590.0},
    "B04": {"mean": 590.0,  "std": 594.0},
    "B05": {"mean": 950.0,  "std": 594.0},
    "B06": {"mean": 1792.0, "std": 572.0},
    "B07": {"mean": 2075.0, "std": 667.0},
    "B08": {"mean": 2218.0, "std": 786.0},
    "B8A": {"mean": 2296.0, "std": 731.0},
    "B09": {"mean": 731.0,  "std": 1023.0},
    "B11": {"mean": 1596.0, "std": 1160.0},
    "B12": {"mean": 1055.0, "std": 1002.0},
}


def load_patch(patch_dir: str, bands: Optional[list] = None, target_size: int = 120) -> Optional[dict]:
    """
    Load a BigEarthNet patch from its directory.

    Args:
        patch_dir: Path to a single BigEarthNet patch directory.
        bands:     List of band names to load (default: all 12).
        target_size: Resample all bands to this spatial size (pixels).

    Returns:
        {
            "patch_name": str,
            "bands": {band_name: np.ndarray},
            "metadata": dict,
        }
        or None if loading fails.
    """
    if not os.path.isdir(patch_dir):
        logger.warning("BigEarthNet patch directory not found: %s", patch_dir)
        return None

    patch_name = os.path.basename(patch_dir)
    if not bands:
        bands = list(BAND_INFO.keys())

    loaded = {}
    meta = {}

    for band in bands:
        tif_path = os.path.join(patch_dir, f"{patch_name}_{band}.tif")
        if not os.path.exists(tif_path):
            logger.debug("Band file missing: %s", tif_path)
            continue
        try:
            arr, band_meta = _read_band(tif_path, target_size)
            if arr is not None:
                loaded[band] = arr
                meta[band] = band_meta
        except Exception as e:
            logger.warning("Failed to load band %s from %s: %s", band, patch_dir, e)

    if not loaded:
        return None

    return {"patch_name": patch_name, "bands": loaded, "metadata": meta}


def normalise_patch(bands_dict: dict) -> dict:
    """
    Normalise each band using BigEarthNet statistics.
    Returns a new dict with the same keys, values normalised to ~[-2, 2].
    """
    try:
        import numpy as np
    except ImportError:
        logger.error("numpy required for normalisation.")
        return bands_dict

    normalised = {}
    for band_name, arr in bands_dict.items():
        stats = BEN_NORM_STATS.get(band_name)
        if stats:
            normalised[band_name] = (arr.astype("float32") - stats["mean"]) / (stats["std"] + 1e-6)
        else:
            # Min-max fallback
            mn, mx = arr.min(), arr.max()
            if mx > mn:
                normalised[band_name] = (arr.astype("float32") - mn) / (mx - mn)
            else:
                normalised[band_name] = arr.astype("float32")

    return normalised


def stack_bands(bands_dict: dict, band_order: Optional[list] = None):
    """
    Stack selected bands into a (C, H, W) numpy array.
    Args:
        bands_dict: dict of {band_name: 2D array}
        band_order: ordered list of band names to include
    Returns: numpy array of shape (C, H, W) or None
    """
    try:
        import numpy as np
    except ImportError:
        return None

    if not band_order:
        band_order = [b for b in BAND_INFO.keys() if b in bands_dict]

    arrays = [bands_dict[b] for b in band_order if b in bands_dict]
    if not arrays:
        return None
    return np.stack(arrays, axis=0)


def _read_band(tif_path: str, target_size: int):
    """Read a single-band GeoTIFF and optionally resize."""
    try:
        import rasterio
        from rasterio.enums import Resampling
        with rasterio.open(tif_path) as src:
            if src.width == target_size and src.height == target_size:
                arr = src.read(1)
            else:
                arr = src.read(
                    1,
                    out_shape=(target_size, target_size),
                    resampling=Resampling.bilinear,
                )
            meta = {
                "crs": str(src.crs),
                "transform": list(src.transform),
                "width": src.width,
                "height": src.height,
                "dtype": str(src.dtypes[0]),
            }
        return arr, meta
    except ImportError:
        # Fallback: PIL
        from PIL import Image as PILImage
        import numpy as np
        img = PILImage.open(tif_path).resize((target_size, target_size))
        return np.array(img), {}
