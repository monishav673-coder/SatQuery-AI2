"""
SATQUERY AI — SAR / Optical+SAR Analysis Model
Pluggable multimodal analysis interface.

Until SAR_MODEL_PATH is configured this returns:
  status = "not_configured"
  error  = "SAR analysis model is not configured."

No fused results are returned unless the model actually ran.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from ml_service.base_model import (
    AnalysisModel, ModelMeta, ModelOutput, ModelStatus, TaskType,
)

logger = logging.getLogger(__name__)

IDENTIFIER = "pluggable-sar-optical-model"
VERSION    = "1.0.0"


class SARModel(AnalysisModel):

    def __init__(self, model_path: str = "", device: str = "cpu") -> None:
        self._device     = device
        self._model_path = model_path
        self._model      = None
        self._load_error: Optional[str] = None
        self._load_time:  Optional[float] = None
        has_path = bool(model_path and os.path.exists(model_path))
        self._status = ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="SAR Analysis",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.SAR_ANALYSIS,
            device=device,
            enabled=has_path,
            status=ModelStatus.NOT_CONFIGURED,
        )

    @property
    def meta(self) -> ModelMeta:
        self._meta.status      = self._status
        self._meta.device      = self._device
        self._meta.error       = self._load_error
        self._meta.load_time_s = self._load_time
        return self._meta

    def _load(self) -> bool:
        if self._model is not None:
            return True
        if not self._model_path or not os.path.exists(self._model_path):
            self._load_error = (
                "SAR model weights not found. "
                "Set SAR_MODEL_PATH in .env to enable SAR / Optical+SAR fusion analysis."
            )
            self._status = ModelStatus.NOT_CONFIGURED
            return False
        try:
            import torch
            self._status = ModelStatus.LOADING
            t0 = time.time()
            try:
                self._model = torch.jit.load(self._model_path, map_location=self._device)
            except Exception:
                self._model = torch.load(self._model_path, map_location=self._device)
            if hasattr(self._model, "eval"):
                self._model.eval()
            self._load_time  = round(time.time() - t0, 2)
            self._status     = ModelStatus.CONFIGURED
            self._load_error = None
            logger.info("SAR model loaded in %.2fs", self._load_time)
            return True
        except ImportError:
            self._load_error = "torch not installed. pip install torch"
            self._status = ModelStatus.NOT_CONFIGURED
            return False
        except Exception as exc:
            self._load_error = str(exc)
            self._status = ModelStatus.FAILED
            return False

    def health_check(self) -> ModelStatus:
        ok = self._load()
        return self._status if ok else ModelStatus.FAILED

    def predict(self, input_data: dict) -> ModelOutput:
        if not self._load():
            return self._not_configured_output(
                self._load_error or "SAR analysis model is not configured."
            )

        optical_path: str = input_data.get("optical_path", "")
        sar_path: str     = input_data.get("sar_path", "")

        for p, label in [(optical_path, "optical"), (sar_path, "SAR")]:
            if not p or not os.path.exists(p):
                return self._failed_output(f"SAR analysis: {label} image not found: {p!r}")

        t0 = time.time()
        try:
            # Subclasses / trained models implement the actual fusion logic here.
            # Placeholder raises NotImplementedError so the caller gets a clean failure.
            raise NotImplementedError(
                "SAR model loaded but fusion inference not implemented. "
                "Override _run_fusion() in a subclass with your model-specific logic."
            )
        except NotImplementedError as exc:
            elapsed = round(time.time() - t0, 3)
            return self._failed_output(str(exc), elapsed)
        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("SAR predict failed")
            return self._failed_output(str(exc), elapsed)
