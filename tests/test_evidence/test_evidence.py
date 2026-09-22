"""
SATQUERY AI — Evidence Validator Tests
Verifies that the EvidenceValidator correctly:
  - passes valid measurements through
  - clears out-of-range values
  - annotates unavailable results honestly
  - never silently propagates fabricated data
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))


from services.evidence_validator import EvidenceValidator, can_transition, assert_transition


# ── Lifecycle state machine ───────────────────────────────────────────────────

class TestLifecycleTransitions:

    def test_valid_pending_to_processing(self):
        assert can_transition("pending", "processing") is True

    def test_valid_processing_to_validating(self):
        assert can_transition("processing", "validating") is True

    def test_valid_validating_to_completed(self):
        assert can_transition("validating", "completed") is True

    def test_invalid_completed_to_processing(self):
        assert can_transition("completed", "processing") is False

    def test_invalid_failed_to_completed(self):
        assert can_transition("failed", "completed") is False

    def test_assert_transition_raises_on_invalid(self):
        with pytest.raises(ValueError, match="Invalid analysis state transition"):
            assert_transition("completed", "processing")

    def test_assert_transition_passes_on_valid(self):
        assert_transition("pending", "processing")   # should not raise


# ── Land cover validation ─────────────────────────────────────────────────────

class TestLandCoverValidation:

    def _run(self, lc_data):
        v = EvidenceValidator()
        result = {"landcover": lc_data}
        return v.validate_result(result)["landcover"]

    def test_valid_classes_pass_through(self):
        lc = {
            "success": True,
            "method": "spectral_heuristic",
            "classes": [
                {"label": "Water", "percentage": 25.0, "area_km2": 1.2, "confidence": 55.0, "direction": "North-East"},
                {"label": "Agriculture / Cropland", "percentage": 75.0, "area_km2": None, "confidence": 40.0, "direction": "South"},
            ],
        }
        out = self._run(lc)
        assert out["classes"][0]["percentage"] == 25.0
        assert out["classes"][1]["percentage"] == 75.0

    def test_percentage_over_100_cleared(self):
        lc = {
            "success": True,
            "method": "spectral_heuristic",
            "classes": [{"label": "Water", "percentage": 150.0, "confidence": 50.0}],
        }
        out = self._run(lc)
        assert out["classes"][0]["percentage"] is None

    def test_negative_percentage_cleared(self):
        lc = {
            "success": True,
            "method": "spectral_heuristic",
            "classes": [{"label": "Forest", "percentage": -5.0, "confidence": 50.0}],
        }
        out = self._run(lc)
        assert out["classes"][0]["percentage"] is None

    def test_negative_area_cleared(self):
        lc = {
            "success": True,
            "method": "spectral_heuristic",
            "classes": [{"label": "Water", "percentage": 10.0, "area_km2": -3.5, "confidence": 50.0}],
        }
        out = self._run(lc)
        assert out["classes"][0]["area_km2"] is None

    def test_coordinate_only_gets_unavailable_status(self):
        lc = {"success": True, "method": "coordinate_only", "classes": []}
        out = self._run(lc)
        assert out["_provenance"]["status"] == "unavailable"

    def test_failed_agent_flagged(self):
        lc = {"success": False, "method": "spectral_heuristic", "classes": []}
        result = {"landcover": lc}
        v = EvidenceValidator()
        validated = v.validate_result(result)
        assert len(validated["_validation_issues"]) > 0


# ── Water validation ─────────────────────────────────────────────────────────

class TestWaterValidation:

    def _run(self, water_data):
        v = EvidenceValidator()
        return v.validate_result({"water": water_data})["water"]

    def test_valid_water_passes(self):
        water = {"success": True, "method": "brightness_heuristic", "water_coverage_pct": 12.4, "water_area_km2": 0.5, "locations": ["North-East"]}
        out = self._run(water)
        assert out["water_coverage_pct"] == 12.4
        assert out["_provenance"]["status"] == "valid"

    def test_over_100_pct_cleared(self):
        water = {"success": True, "method": "brightness_heuristic", "water_coverage_pct": 110.0}
        out = self._run(water)
        assert out["water_coverage_pct"] is None

    def test_negative_area_cleared(self):
        water = {"success": True, "method": "brightness_heuristic", "water_coverage_pct": 5.0, "water_area_km2": -1.2}
        out = self._run(water)
        assert out["water_area_km2"] is None


# ── Building validation ───────────────────────────────────────────────────────

class TestBuildingValidation:

    def _run(self, bld_data):
        v = EvidenceValidator()
        return v.validate_result({"buildings": bld_data})["buildings"]

    def test_null_count_gets_limitation(self):
        bld = {"success": True, "building_count": None, "method": "model_not_configured"}
        out = self._run(bld)
        assert out["building_count"] is None
        assert out["limitation"] is not None

    def test_negative_count_cleared_and_limitation_set(self):
        bld = {"success": True, "building_count": -5, "method": "some_model"}
        out = self._run(bld)
        assert out["building_count"] is None
        assert "limitation" in out

    def test_valid_count_passes_through(self):
        bld = {"success": True, "building_count": 37, "method": "grounding_dino", "confidence": 80.0}
        out = self._run(bld)
        assert out["building_count"] == 37
        assert out["_provenance"]["status"] == "valid"


# ── Change detection validation ───────────────────────────────────────────────

class TestChangeValidation:

    def _run(self, chg_data):
        v = EvidenceValidator()
        return v.validate_result({"change_detection": chg_data})["change_detection"]

    def test_valid_change_passes(self):
        chg = {"success": True, "method": "image_differencing", "overall_change_pct": 23.5, "changes_detected": True}
        out = self._run(chg)
        assert out["overall_change_pct"] == 23.5
        assert out["_provenance"]["status"] == "valid"

    def test_change_over_100_cleared(self):
        chg = {"success": True, "method": "image_differencing", "overall_change_pct": 120.0, "changes_detected": True}
        out = self._run(chg)
        assert out["overall_change_pct"] is None
        assert out["changes_detected"] is False

    def test_failed_change_agent_flagged(self):
        chg = {"success": False, "method": "image_differencing", "overall_change_pct": None}
        result = {"change_detection": chg}
        v = EvidenceValidator()
        validated = v.validate_result(result)
        assert len(validated["_validation_issues"]) > 0


# ── Full result validation ────────────────────────────────────────────────────

class TestFullResultValidation:

    def test_provenance_keys_added(self):
        v = EvidenceValidator()
        result = {
            "landcover":   {"success": True, "method": "spectral_heuristic", "classes": [], "confidence": 45.0},
            "water":       {"success": True, "method": "brightness_heuristic", "water_coverage_pct": 10.0},
            "agriculture": {"success": True, "method": "greenness_heuristic",  "agriculture_pct": 25.0},
            "buildings":   {"success": True, "building_count": None},
        }
        validated = v.validate_result(result)
        assert "_provenance" in validated
        assert "_validation_issues" in validated

    def test_validation_issues_is_list(self):
        v = EvidenceValidator()
        result = {}
        validated = v.validate_result(result)
        assert isinstance(validated["_validation_issues"], list)
