"""
SATQUERY AI — Model Registry
Single source of truth for all ML model instances.
Models are loaded lazily and cached. Status is reported honestly.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from ml_service.base_model import AnalysisModel, ModelStatus

logger = logging.getLogger(__name__)

# Module-level singleton registry
_registry: dict[str, AnalysisModel] = {}
_initialized: bool = False


def _get_device() -> str:
    """Detect compute device without crashing if torch is absent."""
    try:
        import torch
        if torch.cuda.is_available():
            return f"cuda:{torch.cuda.current_device()}"
        return "cpu"
    except ImportError:
        return "cpu"


def initialize_registry(app_config: dict) -> None:
    """
    Called once at application start-up inside the Flask app context.
    Registers models that are enabled in the config.
    Models are NOT yet loaded into memory here — lazy loading happens on first predict().
    """
    global _initialized
    if _initialized:
        return

    device = _get_device()
    logger.info("Model registry initialising. Device: %s", device)

    # ── BLIP Captioning ───────────────────────────────────────────────────
    if app_config.get("BLIP_ENABLED", False):
        try:
            from ml_service.models.blip_caption import BLIPCaptionModel
            _registry["blip"] = BLIPCaptionModel(device=device)
            logger.info("Model registered: blip (NOT YET LOADED)")
        except ImportError as e:
            logger.warning("BLIP registration failed (missing dependency): %s", e)

    # ── BLIP VQA ──────────────────────────────────────────────────────────
    if app_config.get("BLIP_VQA_ENABLED", False):
        try:
            from ml_service.models.blip_vqa import BLIPVQAModel
            _registry["blip_vqa"] = BLIPVQAModel(device=device)
            logger.info("Model registered: blip_vqa (NOT YET LOADED)")
        except ImportError as e:
            logger.warning("BLIP VQA registration failed: %s", e)

    # ── Grounding DINO ────────────────────────────────────────────────────
    if app_config.get("GROUNDING_DINO_ENABLED", False):
        try:
            from ml_service.models.grounding_dino import GroundingDINOModel
            _registry["grounding_dino"] = GroundingDINOModel(device=device)
            logger.info("Model registered: grounding_dino (NOT YET LOADED)")
        except ImportError as e:
            logger.warning("Grounding DINO registration failed: %s", e)

    # ── BigEarthNet Classifier ────────────────────────────────────────────
    if app_config.get("BIGEARTHNET_ENABLED", False):
        model_path = app_config.get("BIGEARTHNET_MODEL_PATH", "")
        if model_path and os.path.exists(model_path):
            try:
                from ml_service.models.bigearthnet_classifier import BigEarthNetClassifier
                _registry["bigearthnet"] = BigEarthNetClassifier(
                    model_path=model_path, device=device
                )
                logger.info("Model registered: bigearthnet")
            except ImportError as e:
                logger.warning("BigEarthNet registration failed: %s", e)
        else:
            logger.info(
                "BigEarthNet: NOT CONFIGURED — set BIGEARTHNET_MODEL_PATH to a valid weights file."
            )

    # ── Change Detection ──────────────────────────────────────────────────
    if app_config.get("CHANGE_DETECTION_ENABLED", False):
        model_path = app_config.get("CHANGE_DETECTION_MODEL_PATH", "")
        if model_path and os.path.exists(model_path):
            try:
                from ml_service.models.change_detection import ChangeDetectionModel
                _registry["change_detection"] = ChangeDetectionModel(
                    model_path=model_path, device=device
                )
                logger.info("Model registered: change_detection")
            except ImportError as e:
                logger.warning("Change detection registration failed: %s", e)
        else:
            logger.info(
                "Change Detection: NOT CONFIGURED — set CHANGE_DETECTION_MODEL_PATH."
            )

    # ── SAR Analysis ──────────────────────────────────────────────────────
    if app_config.get("SAR_ANALYSIS_ENABLED", False):
        model_path = app_config.get("SAR_MODEL_PATH", "")
        if model_path and os.path.exists(model_path):
            try:
                from ml_service.models.sar_model import SARModel
                _registry["sar"] = SARModel(model_path=model_path, device=device)
                logger.info("Model registered: sar")
            except ImportError as e:
                logger.warning("SAR model registration failed: %s", e)
        else:
            logger.info("SAR: NOT CONFIGURED — set SAR_MODEL_PATH.")

    _initialized = True
    configured = [k for k, v in _registry.items()]
    logger.info("Registry ready. Registered models: %s", configured or ["none"])


def get_model(name: str) -> Optional[AnalysisModel]:
    """Retrieve a registered model instance. Returns None if not registered."""
    return _registry.get(name)


def list_models_status() -> dict[str, dict]:
    """
    Return a dict mapping model_name → status dict for the /api/models endpoint.
    Models not in the registry are reported as NOT_CONFIGURED.
    """
    # All possible models the system knows about
    all_models = [
        "blip", "blip_vqa", "grounding_dino",
        "bigearthnet", "change_detection", "sar",
    ]
    result = {}
    for name in all_models:
        model = _registry.get(name)
        if model is None:
            result[name] = {
                "status": ModelStatus.NOT_CONFIGURED,
                "name": name,
                "identifier": "—",
                "device": "—",
                "error": f"{name} is not configured.",
            }
        else:
            meta = model.meta
            result[name] = {
                "status": meta.status,
                "name": meta.name,
                "identifier": meta.identifier,
                "version": meta.version,
                "task": meta.task.value if hasattr(meta.task, "value") else meta.task,
                "device": meta.device,
                "enabled": meta.enabled,
                "error": meta.error,
            }
    return result


def registry_health_check() -> dict[str, str]:
    """
    Run health_check() on every registered model.
    Returns mapping model_name → status string.
    """
    statuses = {}
    for name, model in _registry.items():
        try:
            status = model.health_check()
            statuses[name] = status.value if hasattr(status, "value") else str(status)
        except Exception as exc:
            logger.warning("Health check failed for %s: %s", name, exc)
            statuses[name] = ModelStatus.FAILED.value
    return statuses
