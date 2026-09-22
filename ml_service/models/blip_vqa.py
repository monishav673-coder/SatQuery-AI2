"""
SATQUERY AI — BLIP Visual Question Answering Model
Uses: Salesforce/blip-vqa-base (Hugging Face Transformers)

The question AND the image are both passed to the model.
Answers come from the model — never from templates.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from ml_service.base_model import (
    AnalysisModel, ModelMeta, ModelOutput, ModelStatus, TaskType
)

logger = logging.getLogger(__name__)

IDENTIFIER = "Salesforce/blip-vqa-base"
VERSION = "1.0.0"


class BLIPVQAModel(AnalysisModel):

    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._processor = None
        self._model = None
        self._load_error: Optional[str] = None
        self._load_time: Optional[float] = None
        self._status = ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="BLIP VQA",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.VQA,
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
        if self._model is not None:
            return True
        try:
            from transformers import BlipProcessor, BlipForQuestionAnswering
            import torch

            self._status = ModelStatus.LOADING
            t0 = time.time()

            cache_dir = os.environ.get("MODEL_CACHE_DIR", None)
            self._processor = BlipProcessor.from_pretrained(
                IDENTIFIER, cache_dir=cache_dir
            )
            self._model = BlipForQuestionAnswering.from_pretrained(
                IDENTIFIER, cache_dir=cache_dir
            )
            if self._device.startswith("cuda"):
                self._model = self._model.to(self._device)
            self._model.eval()

            self._load_time = round(time.time() - t0, 2)
            self._status = ModelStatus.CONFIGURED
            self._load_error = None
            logger.info(
                "BLIP VQA loaded in %.2fs on %s", self._load_time, self._device
            )
            return True

        except ImportError:
            msg = (
                "BLIP VQA requires transformers and torch. "
                "Install: pip install transformers torch"
            )
            self._load_error = msg
            self._status = ModelStatus.NOT_CONFIGURED
            logger.warning(msg)
            return False

        except Exception as exc:
            self._load_error = f"BLIP VQA load failed: {exc}"
            self._status = ModelStatus.FAILED
            logger.exception("BLIP VQA load error")
            return False

    def health_check(self) -> ModelStatus:
        if self._model is None:
            ok = self._load()
            return self._status if ok else ModelStatus.FAILED
        return ModelStatus.CONFIGURED

    def predict(self, input_data: dict) -> ModelOutput:
        """
        input_data:
          image_path : str
          question   : str   — required

        Returns:
          data = {
            "question": str,
            "answer": str,
          }
        """
        image_path: str = input_data.get("image_path", "")
        question: str   = input_data.get("question", "").strip()

        if not self._load():
            return self._not_configured_output(
                self._load_error or "BLIP VQA is not configured."
            )

        if not question:
            return self._failed_output("A question must be provided for VQA.")

        if not image_path or not os.path.exists(image_path):
            return self._failed_output(f"Image not found: {image_path!r}")

        t0 = time.time()
        try:
            from PIL import Image as PILImage
            import torch

            img = PILImage.open(image_path).convert("RGB")
            inputs = self._processor(img, question, return_tensors="pt")

            if self._device.startswith("cuda"):
                inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                out = self._model.generate(**inputs)

            answer = self._processor.decode(out[0], skip_special_tokens=True)
            elapsed = round(time.time() - t0, 3)

            logger.info("BLIP VQA answered '%s' in %.3fs", question[:60], elapsed)
            return self._success_output(
                data={"question": question, "answer": answer},
                elapsed=elapsed,
                confidence_available=False,
                metadata={"image_path": image_path},
            )

        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("BLIP VQA predict failed")
            return self._failed_output(str(exc), elapsed)
