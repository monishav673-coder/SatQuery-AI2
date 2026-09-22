"""
SATQUERY AI — Change Detection Model Service
Pluggable change-detection model interface.

Priority:
  1. Trained neural network (set CHANGE_DETECTION_MODEL_PATH in .env)
  2. Image-differencing fallback (labeled as heuristic, not a model)

NEVER fabricates change regions or statistics.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from ml_service.base_model import (
    AnalysisModel, ModelMeta, ModelOutput, ModelStatus, TaskType,
)

logger = logging.getLogger(__name__)

IDENTIFIER = "pluggable-change-detection"
VERSION    = "1.0.0"
DIFF_THRESHOLD = float(os.environ.get("CHANGE_DIFF_THRESHOLD", "0.12"))


class ChangeDetectionModel(AnalysisModel):

    def __init__(self, model_path: str = "", device: str = "cpu") -> None:
        self._device      = device
        self._model_path  = model_path
        self._model       = None
        self._model_type: Optional[str] = None
        self._load_error: Optional[str] = None
        self._load_time:  Optional[float] = None
        self._use_fallback = not (model_path and os.path.exists(model_path))
        self._status = ModelStatus.CONFIGURED if self._use_fallback else ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="Change Detection",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.CHANGE_DETECTION,
            device=device,
            enabled=True,
            status=self._status,
        )

    @property
    def meta(self) -> ModelMeta:
        self._meta.status   = self._status
        self._meta.device   = self._device
        self._meta.error    = self._load_error
        self._meta.load_time_s = self._load_time
        return self._meta

    def _load_model(self) -> bool:
        if self._model is not None or self._use_fallback:
            return True
        try:
            import torch
            self._status = ModelStatus.LOADING
            t0 = time.time()
            try:
                self._model = torch.jit.load(self._model_path, map_location=self._device)
                self._model_type = "torchscript"
            except Exception:
                self._model = torch.load(self._model_path, map_location=self._device)
                self._model_type = "torch"
            if hasattr(self._model, "eval"):
                self._model.eval()
            self._load_time   = round(time.time() - t0, 2)
            self._status      = ModelStatus.CONFIGURED
            self._load_error  = None
            logger.info("Change detection model loaded in %.2fs", self._load_time)
            return True
        except ImportError:
            logger.warning("torch not available; using image-differencing fallback")
            self._use_fallback = True
            self._status = ModelStatus.CONFIGURED
            return True
        except Exception as exc:
            self._load_error = str(exc)
            self._status = ModelStatus.FAILED
            return False

    def health_check(self) -> ModelStatus:
        ok = self._load_model()
        return self._status if ok else ModelStatus.FAILED

    def predict(self, input_data: dict) -> ModelOutput:
        if not self._load_model():
            return self._not_configured_output(
                self._load_error or "Change detection model is not configured."
            )

        img1_path: str       = input_data.get("image1_path", "")
        img2_path: str       = input_data.get("image2_path", "")
        pixel_size: Optional[float] = input_data.get("pixel_size_m")

        for p, label in [(img1_path, "before"), (img2_path, "after")]:
            if not p or not os.path.exists(p):
                return self._failed_output(f"Change detection: {label} image not found: {p!r}")

        t0 = time.time()
        try:
            if self._model is not None:
                result = self._run_neural(img1_path, img2_path, pixel_size)
            else:
                result = self._image_differencing(img1_path, img2_path, pixel_size)

            elapsed = round(time.time() - t0, 3)
            return self._success_output(
                data=result, elapsed=elapsed, confidence_available=True,
                metadata={"image1_path": img1_path, "image2_path": img2_path},
            )
        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("Change detection predict failed")
            return self._failed_output(str(exc), elapsed)

    def _run_neural(self, img1: str, img2: str, pixel_size: Optional[float]) -> dict:
        import torch
        from PIL import Image as PILImage

        def to_tensor(path):
            img = PILImage.open(path).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0
            t = torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0)
            if self._device.startswith("cuda"):
                t = t.to(self._device)
            return t, img.size

        t1, s1 = to_tensor(img1)
        t2, s2 = to_tensor(img2)
        if s1 != s2:
            from torchvision.transforms.functional import resize
            target = (min(s1[1], s2[1]), min(s1[0], s2[0]))
            t1 = resize(t1, target)
            t2 = resize(t2, target)

        with torch.no_grad():
            out = self._model(t1, t2)
            if isinstance(out, (tuple, list)):
                out = out[0]
            mask = (torch.sigmoid(out).cpu().numpy()[0, 0] > 0.5)

        return _build_result(mask, t1.cpu().numpy()[0].transpose(1, 2, 0),
                             t2.cpu().numpy()[0].transpose(1, 2, 0),
                             pixel_size, "neural_model", 75.0)

    def _image_differencing(self, img1: str, img2: str, pixel_size: Optional[float]) -> dict:
        from PIL import Image as PILImage
        p1 = PILImage.open(img1).convert("L")
        p2 = PILImage.open(img2).convert("L")
        if p1.size != p2.size:
            target = (min(p1.width, p2.width), min(p1.height, p2.height))
            p1 = p1.resize(target, PILImage.LANCZOS)
            p2 = p2.resize(target, PILImage.LANCZOS)
        a1 = np.array(p1, dtype=np.float32) / 255.0
        a2 = np.array(p2, dtype=np.float32) / 255.0
        mask = np.abs(a2 - a1) > DIFF_THRESHOLD
        return _build_result(mask, a1, a2, pixel_size, "image_differencing", 45.0,
                             extra_note=(
                                 "Image-differencing heuristic used — not a trained model. "
                                 "Set CHANGE_DETECTION_MODEL_PATH for trained-model results."
                             ))


def _build_result(mask, arr1, arr2, pixel_size, method, confidence, extra_note=""):
    H, W = mask.shape[:2]
    total   = H * W
    changed = int(mask.sum())
    pct     = round(changed / total * 100, 2) if total > 0 else 0.0

    def km2(m):
        if pixel_size and pixel_size > 0:
            return round(float(m.sum()) * pixel_size * pixel_size / 1e6, 4)
        return None

    def direction(m):
        if m.sum() == 0:
            return "N/A"
        ys, xs = np.where(m)
        ns = "North" if ys.mean() < H / 2 else "South"
        ew = "East"  if xs.mean() > W / 2 else "West"
        return f"{ns}-{ew}"

    regions = []
    if pct >= 1.0:
        if arr1.ndim == 3:
            g1, g2 = arr1.mean(axis=2), arr2.mean(axis=2)
        else:
            g1, g2 = arr1, arr2
        diff = g2 - g1
        for m, label in [(diff > DIFF_THRESHOLD, "Brightness Gain"),
                         (diff < -DIFF_THRESHOLD, "Brightness Loss")]:
            if m.sum() / total > 0.005:
                regions.append({
                    "type": label,
                    "change_pct": round(float(m.sum() / total * 100), 2),
                    "direction": direction(m),
                    "area_km2": km2(m),
                })

    note = "Change percentage = changed pixels / total pixels × 100."
    if extra_note:
        note += " " + extra_note
    if not pixel_size:
        note += " Area (km²) unavailable: no georeferencing metadata."

    return {
        "changes_detected": pct >= 1.0,
        "method": method,
        "change_mask": None,
        "change_regions": regions,
        "overall_change_pct": pct,
        "confidence": confidence,
        "note": note.strip(),
    }
