"""
SATQUERY AI — BigEarthNet Dataset Loader
Loads labels and patches from a locally-downloaded BigEarthNet dataset.

Setup:
  1. Download BigEarthNet-S2 from https://bigearth.net/
  2. Set BIGEARTHNET_DATASET_PATH in your .env file to the dataset root.
  3. The labels JSON files must be present per-patch in the standard BigEarthNet structure.

Directory structure expected:
  <BIGEARTHNET_DATASET_PATH>/
    BigEarthNet-v1.0/
      S2A_MSIL2A_20170613T101031_0_45/
        S2A_MSIL2A_20170613T101031_0_45_B02.tif
        ...
        S2A_MSIL2A_20170613T101031_0_45_labels_metadata.json
      ...

If the dataset is not configured, all functions return None or empty results
and log an informative message.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_dataset_path: Optional[str] = None


def _get_dataset_path() -> Optional[str]:
    global _dataset_path
    if _dataset_path:
        return _dataset_path
    try:
        from flask import current_app
        p = current_app.config.get("BIGEARTHNET_DATASET_PATH", "")
    except RuntimeError:
        p = os.environ.get("BIGEARTHNET_DATASET_PATH", "")

    if p and os.path.isdir(p):
        _dataset_path = p
        return _dataset_path

    logger.debug(
        "BigEarthNet dataset not configured or path invalid. "
        "Set BIGEARTHNET_DATASET_PATH in .env to enable dataset-based classification."
    )
    return None


def get_bigearthnet_labels(image_path: str) -> Optional[list]:
    """
    Attempt to retrieve BigEarthNet labels for the image at image_path.

    Looks for a labels_metadata.json file in the same directory as the image
    (standard BigEarthNet patch structure), or in the dataset root.

    Returns a list of label strings or None if not available.
    """
    # Check alongside the image first
    patch_dir = os.path.dirname(image_path)
    patch_name = os.path.splitext(os.path.basename(image_path))[0]

    # Strip band suffix if present (e.g. _B02 → patch name)
    for band in ["_B01", "_B02", "_B03", "_B04", "_B05", "_B06",
                 "_B07", "_B08", "_B8A", "_B09", "_B11", "_B12"]:
        if patch_name.endswith(band):
            patch_name = patch_name[: -len(band)]
            break

    label_file = os.path.join(patch_dir, f"{patch_name}_labels_metadata.json")
    if os.path.exists(label_file):
        return _parse_label_file(label_file)

    # Try dataset path
    dataset_path = _get_dataset_path()
    if not dataset_path:
        return None

    # Search under dataset root
    candidate = os.path.join(dataset_path, "BigEarthNet-v1.0", patch_name,
                             f"{patch_name}_labels_metadata.json")
    if os.path.exists(candidate):
        return _parse_label_file(candidate)

    return None


def _parse_label_file(label_file: str) -> Optional[list]:
    """Parse a BigEarthNet labels_metadata.json file and return label list."""
    try:
        with open(label_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        labels = data.get("labels") or data.get("BigEarthNet-19_labels") or []
        if isinstance(labels, list) and labels:
            logger.info("BigEarthNet labels loaded from %s: %s", label_file, labels)
            return labels
        return None
    except Exception as e:
        logger.warning("Failed to parse BigEarthNet label file %s: %s", label_file, e)
        return None


def list_patches(limit: int = 100) -> list:
    """
    List available BigEarthNet patches in the configured dataset.
    Returns list of patch directory paths (up to `limit`).
    """
    dataset_path = _get_dataset_path()
    if not dataset_path:
        return []

    root = os.path.join(dataset_path, "BigEarthNet-v1.0")
    if not os.path.isdir(root):
        root = dataset_path  # Try root directly

    patches = []
    try:
        for entry in os.scandir(root):
            if entry.is_dir():
                patches.append(entry.path)
            if len(patches) >= limit:
                break
    except Exception as e:
        logger.warning("Error listing BigEarthNet patches: %s", e)

    return patches


def get_patch_stats() -> dict:
    """Return basic statistics about the connected BigEarthNet dataset."""
    patches = list_patches(limit=10_000)
    dataset_path = _get_dataset_path()
    return {
        "configured": dataset_path is not None,
        "dataset_path": dataset_path,
        "patch_count_sampled": len(patches),
        "note": (
            "Patch count is a sample (max 10,000). "
            "Full dataset contains ~590,000 Sentinel-2 patches."
            if dataset_path else
            "Dataset not configured. Set BIGEARTHNET_DATASET_PATH in .env."
        ),
    }
