"""
SATQUERY AI — BLIP Image Captioning Model
Uses: Salesforce/blip-image-captioning-base (Hugging Face Transformers)

This module wraps the real BLIP model.
It will NOT fabricate captions. If the model is unavailable,
it returns status="not_configured" with an explicit error message.
"""

from __future__ import annotations

import logging
import time
import os
from typing import Optional
from dataclasses import dataclass, field

from ml_service.base_model import (
    AnalysisModel, ModelMeta, ModelOutput, ModelStatus, TaskType
)

logger = logging.getLogger(__name__)

IDENTIFIER = "Salesforce/blip-image-captioning-base"
VERSION = "1.0.0"


class BLIPCaptionModel(AnalysisModel):
    """
    Wrapper for Salesforce BLIP image captioning.
    Loads model lazily on first call to predict().
    """

    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._processor = None
        self._model = None
        self._load_error: Optional[str] = None
        self._load_time: Optional[float] = None
        self._status = ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="BLIP Captioning",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.CAPTIONING,
            device=device,
            enabled=True,
            status=ModelStatus.NOT_CONFIGURED,
        )

    @property
    def meta(self) -> ModelMeta:
        self._meta.status = self._status
        self._meta.device = self._device
        self._meta.error = self._load_error
        self._meta.load_time_s = self._load_time
        return self._meta

    def _load(self) -> bool:
        """Load model weights. Returns True on success."""
        if self._model is not None:
            return True
        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            import torch

            self._status = ModelStatus.LOADING
            t0 = time.time()

            cache_dir = os.environ.get("MODEL_CACHE_DIR", None)
            self._processor = BlipProcessor.from_pretrained(
                IDENTIFIER, cache_dir=cache_dir
            )
            self._model = BlipForConditionalGeneration.from_pretrained(
                IDENTIFIER, cache_dir=cache_dir
            )

            # Move to correct device
            if self._device.startswith("cuda"):
                import torch
                self._model = self._model.to(self._device)

            self._model.eval()
            self._load_time = round(time.time() - t0, 2)
            self._status = ModelStatus.CONFIGURED
            self._load_error = None
            logger.info(
                "BLIP Captioning loaded in %.2fs on %s",
                self._load_time, self._device,
            )
            return True

        except ImportError:
            msg = (
                "BLIP requires transformers and torch. "
                "Install with: pip install transformers torch"
            )
            self._load_error = msg
            self._status = ModelStatus.NOT_CONFIGURED
            logger.warning(msg)
            return False

        except Exception as exc:
            self._load_error = f"BLIP load failed: {exc}"
            self._status = ModelStatus.FAILED
            logger.exception("BLIP model load error")
            return False

    def health_check(self) -> ModelStatus:
        if self._model is None:
            ok = self._load()
            return self._status if ok else ModelStatus.FAILED
        return ModelStatus.CONFIGURED

    def predict(self, input_data: dict) -> ModelOutput:
        """
        input_data keys:
          image_path : str   — path to the image file
          prompt     : str   — optional conditional caption prompt

        Returns:
          data = {
            "caption": str,
            "prompt_used": str | None,
          }
        """
        image_path: str = input_data.get("image_path", "")
        prompt: Optional[str] = input_data.get("prompt")

        # ── Guard: model available? ────────────────────────────────────
        if not self._load():
            return self._not_configured_output(self._load_error or "BLIP not available.")

        # ── Guard: image exists? ───────────────────────────────────────
        if not image_path or not os.path.exists(image_path):
            return self._failed_output(
                f"Image not found: {image_path!r}"
            )

        # ── Inference ─────────────────────────────────────────────────
        t0 = time.time()
        try:
            from PIL import Image as PILImage
            import torch

            img = PILImage.open(image_path).convert("RGB")

            if prompt:
                inputs = self._processor(img, prompt, return_tensors="pt")
            else:
                inputs = self._processor(img, return_tensors="pt")

            if self._device.startswith("cuda"):
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                out = self._model.generate(**inputs, max_new_tokens=128)

            caption = self._processor.decode(out[0], skip_special_tokens=True)
            elapsed = round(time.time() - t0, 3)

            logger.info("BLIP caption generated in %.3fs", elapsed)
            return self._success_output(
                data={"caption": caption, "prompt_used": prompt},
                elapsed=elapsed,
                confidence_available=False,   # BLIP captioning doesn't expose scores
                metadata={"image_path": image_path},
            )

        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("BLIP predict failed")
            return self._failed_output(str(exc), elapsed)
