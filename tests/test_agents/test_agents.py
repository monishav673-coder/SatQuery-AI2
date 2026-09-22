"""
SATQUERY AI — Agent Unit Tests
Verifies each agent produces valid output and never fabricates values.
"""

import os
import pytest


# ── Preprocessing agent ───────────────────────────────────────────────────────

class TestPreprocessingAgent:

    def test_valid_image(self, test_image_path):
        from agents.preprocessing_agent import run
        result = run(image_path=test_image_path, role="primary")
        assert result["success"] is True
        assert result["width"] > 0
        assert result["height"] > 0

    def test_no_image_path(self):
        from agents.preprocessing_agent import run
        result = run(image_path=None)
        assert result["success"] is True   # coordinate-only mode
        assert result["width"] is None

    def test_nonexistent_path(self):
        from agents.preprocessing_agent import run
        result = run(image_path="/tmp/does_not_exist_xyz.png")
        assert result["success"] is False

    def test_quality_score_range(self, test_image_path):
        from agents.preprocessing_agent import run
        result = run(image_path=test_image_path)
        if result["quality_score"] is not None:
            assert 0 <= result["quality_score"] <= 100


# ── Water agent ───────────────────────────────────────────────────────────────

class TestWaterAgent:

    def test_water_detection_runs(self, test_image_path):
        from agents.water_agent import run
        result = run(image_path=test_image_path)
        assert result["success"] is True

    def test_water_coverage_in_range(self, test_image_path):
        from agents.water_agent import run
        result = run(image_path=test_image_path)
        pct = result.get("water_coverage_pct")
        if pct is not None:
            assert 0.0 <= pct <= 100.0, f"Water coverage {pct}% out of range"

    def test_no_image_returns_success(self):
        from agents.water_agent import run
        result = run(image_path=None)
        assert result["success"] is True
        assert result.get("water_coverage_pct") is None

    def test_water_level_note_present(self, test_image_path):
        from agents.water_agent import run
        result = run(image_path=test_image_path)
        assert "water_level_note" in result
        assert len(result["water_level_note"]) > 10


# ── Agriculture agent ─────────────────────────────────────────────────────────

class TestAgricultureAgent:

    def test_agriculture_detection_runs(self, test_image_path):
        from agents.agriculture_agent import run
        result = run(image_path=test_image_path)
        assert result["success"] is True

    def test_agriculture_pct_in_range(self, test_image_path):
        from agents.agriculture_agent import run
        result = run(image_path=test_image_path)
        pct = result.get("agriculture_pct")
        if pct is not None:
            assert 0.0 <= pct <= 100.0

    def test_no_image_returns_success(self):
        from agents.agriculture_agent import run
        result = run(image_path=None)
        assert result["success"] is True


# ── Building agent ────────────────────────────────────────────────────────────

class TestBuildingAgent:

    def test_building_agent_no_model_returns_unavailable(self, test_image_path):
        from agents.building_agent import run
        result = run(image_path=test_image_path)
        assert result["success"] is True
        # Without a model, count must be None and limitation must be set
        assert result.get("building_count") is None
        assert result.get("limitation") is not None

    def test_building_agent_never_returns_random_count(self, test_image_path):
        """Run multiple times — count must always be None without a model."""
        from agents.building_agent import run
        for _ in range(3):
            r = run(image_path=test_image_path)
            assert r.get("building_count") is None


# ── Land cover agent ──────────────────────────────────────────────────────────

class TestLandCoverAgent:

    def test_landcover_heuristic_runs(self, app, test_image_path):
        with app.app_context():
            from agents.landcover_agent import run
            result = run(image_path=test_image_path)
            assert result["success"] is True
            assert "classes" in result

    def test_landcover_percentages_sum_approx_100(self, app, test_image_path):
        with app.app_context():
            from agents.landcover_agent import run
            result = run(image_path=test_image_path)
            classes = result.get("classes", [])
            pcts = [c["percentage"] for c in classes if c.get("percentage") is not None]
            if pcts:
                total = sum(pcts)
                assert 90 <= total <= 110, f"Percentages sum to {total} — expected ~100"

    def test_landcover_confidence_in_range(self, app, test_image_path):
        with app.app_context():
            from agents.landcover_agent import run
            result = run(image_path=test_image_path)
            for cls in result.get("classes", []):
                conf = cls.get("confidence")
                if conf is not None:
                    assert 0 <= conf <= 100


# ── Change detection agent ────────────────────────────────────────────────────

class TestChangeDetectionAgent:

    def test_change_detection_two_images(self, test_image_before_path, test_image_after_path):
        from agents.change_detection_agent import run
        result = run(image1_path=test_image_before_path, image2_path=test_image_after_path)
        assert result["success"] is True
        assert "changes_detected" in result
        assert "overall_change_pct" in result

    def test_change_pct_in_range(self, test_image_before_path, test_image_after_path):
        from agents.change_detection_agent import run
        result = run(image1_path=test_image_before_path, image2_path=test_image_after_path)
        pct = result.get("overall_change_pct")
        if pct is not None:
            assert 0.0 <= pct <= 100.0

    def test_change_detection_missing_image(self, test_image_before_path):
        from agents.change_detection_agent import run
        result = run(image1_path=test_image_before_path, image2_path=None)
        assert result["success"] is True
        # Must report insufficient data, not crash
        assert "insufficient" in result.get("notes", [""])[0].lower() or \
               result.get("method") == "insufficient_data"

    def test_identical_images_no_change(self, test_image_path):
        from agents.change_detection_agent import run
        result = run(image1_path=test_image_path, image2_path=test_image_path)
        assert result["success"] is True
        # Same image → minimal or no change
        pct = result.get("overall_change_pct", 0)
        assert pct < 5.0, f"Same images should show near-zero change, got {pct}%"


# ── Confidence agent ──────────────────────────────────────────────────────────

class TestConfidenceAgent:

    def test_confidence_returns_value(self, test_image_path):
        from agents.preprocessing_agent import run as pre_run
        from agents.water_agent         import run as water_run
        from agents.confidence_agent    import run as conf_run
        pre    = pre_run(image_path=test_image_path)
        water  = water_run(image_path=test_image_path)
        result = conf_run(pre_result=pre, water_result=water, mode="single", input_type="image")
        assert "overall_confidence" in result
        oc = result["overall_confidence"]
        assert 0 <= oc <= 100, f"Confidence {oc} out of range"

    def test_coordinate_only_caps_confidence(self):
        from agents.confidence_agent import run as conf_run
        result = conf_run(mode="single", input_type="coordinates")
        oc = result["overall_confidence"]
        assert oc <= 45.0, "Coordinate-only should have low confidence"

    def test_confidence_explanation_present(self):
        from agents.confidence_agent import run as conf_run
        result = conf_run(mode="single", input_type="image")
        assert "explanation" in result
        assert len(result["explanation"]) > 10
