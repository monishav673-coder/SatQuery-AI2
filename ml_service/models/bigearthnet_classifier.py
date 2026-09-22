"""
SATQUERY AI — BigEarthNet-Compatible Land Cover Classifier
Loads a trained multi-label classification model (19-class or 43-class)
compatible with the BigEarthNet dataset and nomenclature.

Supported model formats: ONNX, PyTorch (.pt / .pth), or torchscript.
Set BIGEARTHNET_MODEL_PATH in .env to a trained weights file.
Set BIGEARTHNET_NUM_CLASSES to 19 (default) or 43.

If the model is not configured, this module returns:
  status = "not_configured"
  error  = "BigEarthNet classifier is not configured."

BigEarthNet dataset: https://bigearth.net/
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from ml_service.base_model import (
    AnalysisModel, ModelMeta, ModelOutput, ModelStatus, TaskType
)
from data.bigearthnet.labels import BEN_19_CLASSES, BEN_43_CLASSES, get_display_class

logger = logging.getLogger(__name__)

IDENTIFIER = "BigEarthNet-compatible-classifier"
VERSION = "1.0.0"


class BigEarthNetClassifier(AnalysisModel):
    """
    Multi-label land-cover classifier trained on BigEarthNet dataset.

    Input: pre-processed Sentinel-2 patch (stacked numpy array, C×H×W)
           or a path to a GeoTIFF with the expected band configuration.
    Output: multi-hot label vector + per-class probabilities.

    NOTE: Area percentages are NOT inferred from classification probabilities
    alone — classification scores ≠ land-cover percentage.
    Results are labeled explicitly as "model classification output, not
    geographic area measurement."
    """

    def __init__(self, model_path: str, device: str = "cpu") -> None:
        self._device = device
        self._model_path = model_path
        self._model = None
        self._model_type: Optional[str] = None  # "onnx" | "torch" | "torchscript"
        self._load_error: Optional[str] = None
        self._load_time: Optional[float] = None
        self._num_classes = int(os.environ.get("BIGEARTHNET_NUM_CLASSES", "19"))
        self._classes = BEN_19_CLASSES if self._num_classes == 19 else BEN_43_CLASSES
        self._status = ModelStatus.NOT_CONFIGURED
        self._meta = ModelMeta(
            name="BigEarthNet Classifier",
            identifier=IDENTIFIER,
            version=VERSION,
            task=TaskType.CLASSIFICATION,
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
        if not self._model_path or not os.path.exists(self._model_path):
            self._load_error = (
                f"BigEarthNet model weights not found at {self._model_path!r}. "
                "Set BIGEARTHNET_MODEL_PATH in .env to a valid weights file."
            )
            self._status = ModelStatus.NOT_CONFIGURED
            return False

        ext = os.path.splitext(self._model_path)[1].lower()
        t0 = time.time()
        self._status = ModelStatus.LOADING

        # ── Try ONNX Runtime ──────────────────────────────────────────
        if ext == ".onnx":
            try:
                import onnxruntime as ort
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if self._device.startswith("cuda")
                    else ["CPUExecutionProvider"]
                )
                self._model = ort.InferenceSession(
                    self._model_path, providers=providers
                )
                self._model_type = "onnx"
                self._load_time = round(time.time() - t0, 2)
                self._status = ModelStatus.CONFIGURED
                logger.info("BigEarthNet ONNX model loaded in %.2fs", self._load_time)
                return True
            except ImportError:
                logger.warning("onnxruntime not installed; falling through to torch.")
            except Exception as exc:
                self._load_error = f"ONNX load failed: {exc}"
                self._status = ModelStatus.FAILED
                return False

        # ── Try PyTorch ───────────────────────────────────────────────
        try:
            import torch
            # Try torchscript first
            try:
                self._model = torch.jit.load(
                    self._model_path,
                    map_location=self._device,
                )
                self._model_type = "torchscript"
            except Exception:
                self._model = torch.load(
                    self._model_path,
                    map_location=self._device,
                )
                self._model_type = "torch"

            if hasattr(self._model, "eval"):
                self._model.eval()

            self._load_time = round(time.time() - t0, 2)
            self._status = ModelStatus.CONFIGURED
            logger.info("BigEarthNet torch model loaded in %.2fs", self._load_time)
            return True

        except ImportError:
            self._load_error = (
                "Neither onnxruntime nor torch is installed. "
                "Install: pip install onnxruntime OR pip install torch"
            )
            self._status = ModelStatus.NOT_CONFIGURED
            return False

        except Exception as exc:
            self._load_error = f"BigEarthNet model load failed: {exc}"
            self._status = ModelStatus.FAILED
            logger.exception("BigEarthNet model load error")
            return False

    def health_check(self) -> ModelStatus:
        if self._model is None:
            ok = self._load()
            return self._status if ok else ModelStatus.FAILED
        return ModelStatus.CONFIGURED

    def predict(self, input_data: dict) -> ModelOutput:
        """
        input_data:
          image_path    : str   — path to GeoTIFF or patch dir for band loading
          patch_array   : np.ndarray (optional) — pre-loaded (C, H, W) patch

        Returns:
          data = {
            "labels_detected": [str, ...],          # class labels with prob > threshold
            "probabilities": {label: float, ...},   # per-class sigmoid output
            "display_classes": [str, ...],           # mapped to SATQUERY display classes
            "num_classes": int,
            "threshold": float,
            "note": str,                             # explains what classification means
          }
        """
        if not self._load():
            return self._not_configured_output(
                self._load_error or "BigEarthNet classifier is not configured."
            )

        image_path: str = input_data.get("image_path", "")
        patch_array = input_data.get("patch_array")

        # ── Prepare input tensor ───────────────────────────────────────
        t0 = time.time()
        try:
            arr = self._prepare_input(image_path, patch_array)
            if arr is None:
                return self._failed_output(
                    "Could not prepare input array. Check image path and band configuration."
                )

            probs = self._run_inference(arr)
            if probs is None:
                return self._failed_output("Model inference returned no output.")

            threshold = float(os.environ.get("BIGEARTHNET_THRESHOLD", "0.5"))
            labels_detected = [
                self._classes[i]
                for i, p in enumerate(probs)
                if p > threshold and i < len(self._classes)
            ]
            prob_dict = {
                cls: round(float(probs[i]), 4)
                for i, cls in enumerate(self._classes)
                if i < len(probs)
            }
            display_classes = list({get_display_class(lbl) for lbl in labels_detected})

            elapsed = round(time.time() - t0, 3)
            logger.info(
                "BigEarthNet classified %d labels in %.3fs", len(labels_detected), elapsed
            )
            return self._success_output(
                data={
                    "labels_detected": labels_detected,
                    "probabilities": prob_dict,
                    "display_classes": display_classes,
                    "num_classes": self._num_classes,
                    "threshold": threshold,
                    "note": (
                        "These are model classification labels derived from spectral signatures. "
                        "They indicate land cover types present in the image, NOT geographic area percentages. "
                        "Area calculation requires geospatial metadata."
                    ),
                },
                elapsed=elapsed,
                confidence_available=True,
                metadata={
                    "model_type": self._model_type,
                    "image_path": image_path,
                    "dataset": "BigEarthNet",
                    "nomenclature": f"{self._num_classes}-class",
                },
            )

        except Exception as exc:
            elapsed = round(time.time() - t0, 3)
            logger.exception("BigEarthNet predict failed")
            return self._failed_output(str(exc), elapsed)

    def _prepare_input(self, image_path: str, patch_array) -> Optional[np.ndarray]:
        """
        Returns a (1, C, H, W) numpy float32 array for model input.
        Tries patch_array first, then loads from GeoTIFF / patch dir.
        """
        if patch_array is not None and isinstance(patch_array, np.ndarray):
            arr = patch_array.astype(np.float32)
            if arr.ndim == 3:
                arr = arr[np.newaxis, ...]  # add batch dim
            return arr

        # Load from BigEarthNet patch directory
        if image_path and os.path.isdir(image_path):
            from data.bigearthnet.preprocessing import load_patch, normalise_patch, stack_bands
            patch_data = load_patch(image_path)
            if patch_data:
                normalised = normalise_patch(patch_data["bands"])
                stacked = stack_bands(normalised)
                if stacked is not None:
                    return stacked[np.newaxis, ...].astype(np.float32)

        # Load from GeoTIFF
        if image_path and os.path.isfile(image_path):
            try:
                import rasterio
                with rasterio.open(image_path) as src:
                    arr = src.read().astype(np.float32)  # (C, H, W)
                    return arr[np.newaxis, ...]
            except Exception:
                pass
            try:
                from PIL import Image as PILImage
                img = PILImage.open(image_path).convert("RGB")
                arr = np.array(img).transpose(2, 0, 1).astype(np.float32) / 255.0
                return arr[np.newaxis, ...]
            except Exception:
                pass

        return None

    def _run_inference(self, arr: np.ndarray) -> Optional[np.ndarray]:
        """Run inference and return sigmoid probabilities as (num_classes,) array."""
        if self._model_type == "onnx":
            input_name = self._model.get_inputs()[0].name
            outputs = self._model.run(None, {input_name: arr})
            logits = outputs[0][0]  # (num_classes,)
            return _sigmoid(logits)

        # PyTorch / torchscript
        import torch
        tensor = torch.from_numpy(arr)
        if self._device.startswith("cuda"):
            tensor = tensor.to(self._device)
        with torch.no_grad():
            out = self._model(tensor)
            if isinstance(out, (tuple, list)):
                out = out[0]
            logits = out.cpu().numpy()[0]  # (num_classes,)
        return _sigmoid(logits)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))
