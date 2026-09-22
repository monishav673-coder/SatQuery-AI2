"""
SATQUERY AI — Model Service Interface
Every ML model in the system implements this base class.
This enforces: consistent output schema, provenance, honest status reporting.
"""

from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import uuid

logger = logging.getLogger(__name__)


class ModelStatus(str, Enum):
    CONFIGURED   = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED       = "FAILED"
    LOADING      = "LOADING"
    UNAVAILABLE  = "UNAVAILABLE"


class TaskType(str, Enum):
    CAPTIONING        = "captioning"
    VQA               = "vqa"
    OBJECT_DETECTION  = "object_detection"
    CLASSIFICATION    = "classification"
    CHANGE_DETECTION  = "change_detection"
    SAR_ANALYSIS      = "sar_analysis"
    SEGMENTATION      = "segmentation"


@dataclass
class ModelMeta:
    name: str
    identifier: str        # e.g. "Salesforce/blip-image-captioning-base"
    version: str           # e.g. "1.0.0" or commit SHA
    task: TaskType
    device: str            # "cuda" | "cpu" | "unknown"
    enabled: bool
    status: ModelStatus
    error: Optional[str]   = None
    load_time_s: Optional[float] = None
    supported_input_types: list[str] = field(default_factory=lambda: ["jpg", "jpeg", "png", "tiff"])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["task"] = self.task.value
        d["status"] = self.status.value
        return d


@dataclass
class ModelOutput:
    """
    Standardised output from every model call.
    Never populate analytical fields unless the model actually ran.
    """
    model_name: str
    model_identifier: str
    model_version: str
    execution_id: str
    status: str                       # "success" | "failed" | "not_configured" | "unavailable"
    task: str
    device: str
    execution_time_s: Optional[float]
    data: Optional[dict]              # domain-specific payload
    error: Optional[str]
    confidence_available: bool
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "model_identifier": self.model_identifier,
            "model_version": self.model_version,
            "execution_id": self.execution_id,
            "status": self.status,
            "task": self.task,
            "device": self.device,
            "execution_time_s": self.execution_time_s,
            "data": self.data,
            "error": self.error,
            "confidence_available": self.confidence_available,
            "metadata": self.metadata,
        }


class AnalysisModel(abc.ABC):
    """
    Abstract base class all SATQUERY AI ML models must implement.
    """

    @property
    @abc.abstractmethod
    def meta(self) -> ModelMeta:
        """Return model metadata / current status."""
        ...

    @abc.abstractmethod
    def health_check(self) -> ModelStatus:
        """
        Check whether the model is available and functional.
        Returns ModelStatus without raising.
        """
        ...

    @abc.abstractmethod
    def predict(self, input_data: dict) -> ModelOutput:
        """
        Run inference.  Must NEVER return fabricated data.
        If unavailable, return ModelOutput with status='not_configured' / 'failed'.
        """
        ...

    # ── helpers available to all subclasses ───────────────────────────────

    def _not_configured_output(self, reason: str = "") -> ModelOutput:
        return ModelOutput(
            model_name=self.meta.name,
            model_identifier=self.meta.identifier,
            model_version=self.meta.version,
            execution_id=str(uuid.uuid4()),
            status="not_configured",
            task=self.meta.task.value,
            device=self.meta.device,
            execution_time_s=None,
            data=None,
            error=reason or f"{self.meta.name} is not configured.",
            confidence_available=False,
        )

    def _failed_output(self, error: str, elapsed: float = 0.0) -> ModelOutput:
        return ModelOutput(
            model_name=self.meta.name,
            model_identifier=self.meta.identifier,
            model_version=self.meta.version,
            execution_id=str(uuid.uuid4()),
            status="failed",
            task=self.meta.task.value,
            device=self.meta.device,
            execution_time_s=elapsed,
            data=None,
            error=error,
            confidence_available=False,
        )

    def _success_output(self, data: dict, elapsed: float,
                        confidence_available: bool = True,
                        metadata: Optional[dict] = None) -> ModelOutput:
        return ModelOutput(
            model_name=self.meta.name,
            model_identifier=self.meta.identifier,
            model_version=self.meta.version,
            execution_id=str(uuid.uuid4()),
            status="success",
            task=self.meta.task.value,
            device=self.meta.device,
            execution_time_s=elapsed,
            data=data,
            error=None,
            confidence_available=confidence_available,
            metadata=metadata or {},
        )
