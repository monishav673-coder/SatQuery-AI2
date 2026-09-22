"""
SATQUERY AI — Grounding DINO Object Detection Model
Implements real inference using the groundingdino library.

Building counts are derived from actual detections only.
No default / fallback count is ever returned.

Installation:
  pip install groundingdino-py
  OR
  pip install git+https://github.com/IDEA-Research/GroundingDINO.git

Model weights (download separately):
  wget https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth
  Set GROUNDING_DINO_WEIGHTS_PATH in .env
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

IDENTIFIER = "IDEA-Research/grounding-dino-tiny"
VERSION    = "0.1.0"

# Default confidence threshold — only return detections above this score
DEFAULT_BOX_THRESHOLD  = 0.35
DEFAULT_TEXT_THRESHOLD = 0.25


class GroundingDINOModel(AnalysisModel):
    """
    Grounding DINO: open-vocabulary object detection using text prompts.
    Returns bounding boxes, labels, and confidence scores from real inference.
    Building count = len([d for d in detections if 'building' in d.label])
    """

    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._model = None
        self._load_error: Optional[str] = None
        self._load_time: Optional[float] = None
        self._weights_path = os.environ.get("GROUNDING_DINO_WEIGHTS_PATH", "")
        self._config_path  = os.environ.get("GROUNDING_DINO_CONFIG_PATH", "")
        self._status = ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="Grounding DINO",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.OBJECT_DETECTION,
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

        if not self._weights_path or not os.path.exists(self._weights_path):
            self._load_error = (
                "Grounding DINO weights not found. "
                "Download groundingdino_swint_ogc.pth and set GROUNDING_DINO_WEIGHTS_PATH in .env"
            )
            self._status = ModelStatus.NOT_CONFIGURED
            return False

        try:
            # Try loading via groundingdino library
            from groundingdino.util.inference import load_model
            import torch

            self._status = ModelStatus.LOADING
            t0 = time.time()

            # Config path — use bundled default if not specified
            config = self._config_path or self._find_default_config()
            if not config:
                self._load_error = (
                    "Grounding DINO config not found. "
                    "Set GROUNDING_DINO_CONFIG_PATH in .env"
                )
                self._status = ModelStatus.NOT_CONFIGURED
                return False

            self._model = load_model(config, self._weights_path)
            if self._device.startswith("cuda"):
                self._model = self._model.to(self._device)
            self._model.eval()

            self._load_time = round(time.time() - t0, 2)
            self._status = ModelStatus.CONFIGURED
            self._load_error = None
            logger.info(
                "Grounding DINO loaded in %.2fs on %s",
                self._load_time, self._device,
            )
            return True

        except ImportError:
            self._load_error = (
                "groundingdino library not installed. "
                "Install: pip install groundingdino-py"
            )
            self._status = ModelStatus.NOT_CONFIGURED
            logger.warning(self._load_error)
            return False

        except Exception as exc:
            self._load_error = f"Grounding DINO load failed: {exc}"
            self._status = ModelStatus.FAILED
            logger.exception("Grounding DINO load error")
            return False

    def _find_default_config(self) -> Optional[str]:
        """Try to locate the bundled GroundingDINO config file."""
        try:
            import groundingdino
            pkg_dir = os.path.dirname(groundingdino.__file__)
            config = os.path.join(
                pkg_dir, "config", "GroundingDINO_SwinT_OGC.py"
            )
            return config if os.path.exists(config) else None
        except Exception:
            return None

    def health_check(self) -> ModelStatus:
        if self._model is None:
            ok = self._load()
            return self._status if ok else ModelStatus.FAILED
        return ModelStatus.CONFIGURED

    def predict(self, input_data: dict) -> ModelOutput:
        """
        input_data:
          image_path      : str   — path to image
          text_prompt     : str   — e.g. "building . road . water body . tree"
          box_threshold   : float — default 0.35
          text_threshold  : float — default 0.25

        Returns:
          data = {
            "detections": [
              {
                "label": str,
                "score": float,
                "box": [x_min, y_min, x_max, y_max],  # absolute pixel coords
                "box_relative": [cx, cy, w, h],        # 0-1 normalised (DINO format)
              }
            ],
            "detection_count": int,
            "label_counts": {"building": 3, "road": 1, ...},
            "annotated_image_path": str | None,
          }
        """
        if not self._load():
            return self._not_configured_output(
                self._load_error or "Grounding DINO is not configured."
            )

        image_path: str   = input_data.get("image_path", "")
        text_prompt: str  = input_data.get("text_prompt", "building")
        box_thr: float    = float(input_data.get("box_threshold", DEFAULT_BOX_THRESHOLD))
        text_thr: float   = float(input_data.get("text_threshold", DEFAULT_TEXT_THRESHOLD))

        if not image_path or not os.path.exists(image_path):
            return self._failed_output(f"Image not found: {image_path!r}")

        t0 = time.time()
        try:
            from groundingdino.util.inference import predict as dino_predict, annotate
            import torch
            import numpy as np
            from PIL import Image as PILImage

            # ── Load + preprocess image ────────────────────────────────
            img_pil = PILImage.open(image_path).convert("RGB")
            img_w, img_h = img_pil.size

            # Grounding DINO expects a specific transform
            from groundingdino.util.inference import load_image
            img_src, img_tensor = load_image(image_path)

            if self._device.startswith("cuda"):
                img_tensor = img_tensor.to(self._device)

            # ── Run inference ──────────────────────────────────────────
            boxes, logits, phrases = dino_predict(
                model=self._model,
                image=img_tensor,
                caption=text_prompt,
                box_threshold=box_thr,
                text_threshold=text_thr,
            )

            # boxes are [cx, cy, w, h] normalised to 0-1
            detections = []
            label_counts: dict[str, int] = {}

            for box_rel, score, phrase in zip(
                boxes.cpu().numpy(), logits.cpu().numpy(), phrases
            ):
                cx, cy, w, h = box_rel
                x_min = int((cx - w / 2) * img_w)
                y_min = int((cy - h / 2) * img_h)
                x_max = int((cx + w / 2) * img_w)
                y_max = int((cy + h / 2) * img_h)

                # Clamp to image bounds
                x_min = max(0, x_min); y_min = max(0, y_min)
                x_max = min(img_w, x_max); y_max = min(img_h, y_max)

                det = {
                    "label": phrase.strip(),
                    "score": round(float(score), 4),
                    "box": [x_min, y_min, x_max, y_max],
                    "box_relative": [round(float(v), 6) for v in box_rel],
                }
                detections.append(det)
                label_counts[phrase.strip()] = label_counts.get(phrase.strip(), 0) + 1

            # ── Generate annotated image ───────────────────────────────
            annotated_path = None
            try:
                import cv2
                annotated = annotate(
                    image_source=img_src,
                    boxes=boxes,
                    logits=logits,
                    phrases=phrases,
                )
                upload_dir = os.environ.get("UPLOAD_FOLDER", "/tmp")
                fname = f"dino_{os.path.basename(image_path)}"
                annotated_path = os.path.join(upload_dir, fname)
                cv2.imwrite(annotated_path, annotated)
            except Exception as ann_err:
                logger.debug("Annotation failed (non-fatal): %s", ann_err)

            elapsed = round(time.time() - t0, 3)
            logger.info(
                "Grounding DINO: %d detections for prompt '%s' in %.3fs",
                len(detections), text_prompt[:60], elapsed,
            )

            return self._success_output(
                data={
                    "detections": detections,
                    "detection_count": len(detections),
                    "label_counts": label_counts,
                    "text_prompt": text_prompt,
                    "box_threshold": box_thr,
                    "text_threshold": text_thr,
                    "annotated_image_path": annotated_path,
                    "image_width": img_w,
                    "image_height": img_h,
                },
                elapsed=elapsed,
                confidence_available=True,
                metadata={"image_path": image_path},
            )

        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("Grounding DINO predict failed")
            return self._failed_output(str(exc), elapsed)
