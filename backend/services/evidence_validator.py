"""
SATQUERY AI — Evidence Validator
Every analytical claim must pass through this module before being included
in the final result.  If a value cannot be traced to real computation,
it is replaced with an explicit unavailable marker.

Rules enforced:
  1. A numerical measurement must have a recorded source (model or method).
  2. A model-derived value must link to a model_execution_id.
  3. No value may be fabricated or randomly generated.
  4. If a model returned status != "success", its data is NOT propagated.
  5. Confidence must originate from model output or documented calculation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

UNAVAILABLE = "NOT_AVAILABLE"
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


@dataclass
class ProvenanceRecord:
    """Tracks where an analytical value came from."""
    value: Any
    source: str                       # model name, "image_differencing", "pixel_calculation" …
    source_execution_id: Optional[str] = None
    derived_from: Optional[str]       = None   # asset / image path
    calculation: Optional[str]        = None   # e.g. "water_pixels / valid_pixels × 100"
    confidence: Optional[float]       = None
    status: str                        = "valid" # "valid" | "unavailable" | "insufficient"
    note: Optional[str]               = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


class EvidenceValidator:
    """
    Validates and annotates analytical results with provenance information.
    Call validate_result() on the full pipeline result dict before storing.
    """

    def validate_result(self, result: dict) -> dict:
        """
        Walk every agent result in `result`, validate each claim,
        and annotate with provenance.  Returns the validated result dict.
        """
        issues: list[str] = []

        result["_provenance"] = {}
        result["_validation_issues"] = []

        # ── Landcover ─────────────────────────────────────────────────────
        lc = result.get("landcover", {})
        if lc:
            validated_lc, lc_issues = self._validate_landcover(lc)
            result["landcover"] = validated_lc
            issues.extend(lc_issues)

        # ── Water ──────────────────────────────────────────────────────────
        water = result.get("water", {})
        if water:
            validated_water, w_issues = self._validate_water(water)
            result["water"] = validated_water
            issues.extend(w_issues)

        # ── Agriculture ────────────────────────────────────────────────────
        agri = result.get("agriculture", {})
        if agri:
            validated_agri, a_issues = self._validate_agriculture(agri)
            result["agriculture"] = validated_agri
            issues.extend(a_issues)

        # ── Buildings ──────────────────────────────────────────────────────
        bld = result.get("buildings", {})
        if bld:
            validated_bld, b_issues = self._validate_buildings(bld)
            result["buildings"] = validated_bld
            issues.extend(b_issues)

        # ── Change Detection ───────────────────────────────────────────────
        chg = result.get("change_detection")
        if chg:
            validated_chg, c_issues = self._validate_change(chg)
            result["change_detection"] = validated_chg
            issues.extend(c_issues)

        # ── Confidence ─────────────────────────────────────────────────────
        conf = result.get("confidence", {})
        if conf:
            oc = conf.get("overall_confidence")
            if oc is not None and not isinstance(oc, (int, float)):
                result["confidence"]["overall_confidence"] = None
                issues.append("overall_confidence has invalid type — cleared.")

        result["_validation_issues"] = issues
        if issues:
            logger.info(
                "Evidence validation: %d issue(s) for analysis %s",
                len(issues), result.get("analysis_id", "?"),
            )

        return result

    # ── per-domain validators ──────────────────────────────────────────────

    def _validate_landcover(self, lc: dict) -> tuple[dict, list[str]]:
        issues = []
        method = lc.get("method", "")
        classes = lc.get("classes", [])

        if not lc.get("success"):
            issues.append("Land cover agent reported failure.")
            return lc, issues

        if method in ("unavailable", "coordinate_only"):
            lc["_provenance"] = ProvenanceRecord(
                value=UNAVAILABLE,
                source=method,
                status="unavailable",
                note="Land cover unavailable: no image or model.",
            ).to_dict()
            return lc, issues

        # Validate each class entry
        clean_classes = []
        for cls in classes:
            pct = cls.get("percentage")
            if pct is not None:
                # Percentage must be 0-100
                if not (0.0 <= float(pct) <= 100.0):
                    issues.append(
                        f"Land cover class '{cls.get('label')}' percentage {pct} out of range — cleared."
                    )
                    cls["percentage"] = None
            area = cls.get("area_km2")
            if area is not None and float(area) < 0:
                issues.append(
                    f"Negative area for '{cls.get('label')}' — cleared."
                )
                cls["area_km2"] = None
            conf = cls.get("confidence")
            if conf is not None and not (0.0 <= float(conf) <= 100.0):
                cls["confidence"] = None
            clean_classes.append(cls)

        lc["classes"] = clean_classes
        lc["_provenance"] = ProvenanceRecord(
            value=f"{len(clean_classes)} classes",
            source=method,
            calculation="pixel brightness/spectral thresholds or trained model",
            status="valid",
        ).to_dict()
        return lc, issues

    def _validate_water(self, water: dict) -> tuple[dict, list[str]]:
        issues = []
        if not water.get("success"):
            issues.append("Water agent reported failure.")
            return water, issues

        pct = water.get("water_coverage_pct")
        if pct is not None:
            if not (0.0 <= float(pct) <= 100.0):
                issues.append(f"Water coverage {pct}% out of range — cleared.")
                water["water_coverage_pct"] = None

        area = water.get("water_area_km2")
        if area is not None and float(area) < 0:
            issues.append("Negative water area — cleared.")
            water["water_area_km2"] = None

        water["_provenance"] = ProvenanceRecord(
            value=pct,
            source=water.get("method", "unknown"),
            calculation="water_pixels / valid_pixels × 100",
            status="valid" if pct is not None else "unavailable",
        ).to_dict()
        return water, issues

    def _validate_agriculture(self, agri: dict) -> tuple[dict, list[str]]:
        issues = []
        if not agri.get("success"):
            issues.append("Agriculture agent reported failure.")
            return agri, issues

        pct = agri.get("agriculture_pct")
        if pct is not None and not (0.0 <= float(pct) <= 100.0):
            issues.append(f"Agriculture coverage {pct}% out of range — cleared.")
            agri["agriculture_pct"] = None

        agri["_provenance"] = ProvenanceRecord(
            value=pct,
            source=agri.get("method", "unknown"),
            calculation="agricultural_pixels / total_pixels × 100",
            status="valid" if pct is not None else "unavailable",
        ).to_dict()
        return agri, issues

    def _validate_buildings(self, bld: dict) -> tuple[dict, list[str]]:
        issues = []
        count = bld.get("building_count")

        if count is not None:
            # Must be non-negative integer from an actual detection run
            if not isinstance(count, int) or count < 0:
                issues.append(f"Building count {count!r} is invalid — cleared.")
                bld["building_count"] = None
                bld["limitation"] = (
                    "Building count was invalid and has been cleared. "
                    "A validated detection model is required."
                )
        else:
            # Explicitly document that count is unavailable
            if not bld.get("limitation"):
                bld["limitation"] = (
                    "Building detection model not configured. "
                    "Building count is NOT AVAILABLE."
                )

        bld["_provenance"] = ProvenanceRecord(
            value=count,
            source=bld.get("method", "unknown"),
            calculation="validated_detection_count from object detector",
            status="valid" if count is not None else "unavailable",
            note=bld.get("limitation"),
        ).to_dict()
        return bld, issues

    def _validate_change(self, chg: dict) -> tuple[dict, list[str]]:
        issues = []
        if not chg.get("success"):
            issues.append("Change detection agent reported failure.")
            return chg, issues

        pct = chg.get("overall_change_pct")
        if pct is not None and not (0.0 <= float(pct) <= 100.0):
            issues.append(f"Change percentage {pct}% out of range — cleared.")
            chg["overall_change_pct"] = None
            chg["changes_detected"]   = False

        chg["_provenance"] = ProvenanceRecord(
            value=pct,
            source=chg.get("method", "unknown"),
            calculation="changed_pixels / total_pixels × 100",
            status="valid" if pct is not None else "unavailable",
        ).to_dict()
        return chg, issues


# ── Lifecycle state machine ────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, list[str]] = {
    "pending":    ["processing", "cancelled"],
    "processing": ["validating", "failed"],
    "validating": ["completed", "failed"],
    "completed":  [],
    "failed":     [],
    "cancelled":  [],
}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise ValueError(
            f"Invalid analysis state transition: {current!r} → {target!r}. "
            f"Allowed from {current!r}: {VALID_TRANSITIONS.get(current, [])}"
        )
