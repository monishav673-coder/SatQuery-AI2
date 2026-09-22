"""
SATQUERY AI — Analysis API Tests
Covers: file upload, validation, authorization, error responses,
        analysis lifecycle, history, and report generation.
"""

import io
import uuid
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _png_file(name="test.png"):
    """Create an in-memory PNG file tuple for multipart upload."""
    from PIL import Image as PILImage
    import numpy as np
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    arr[:32, :32] = [20, 40, 120]
    arr[32:, 32:] = [130, 130, 130]
    buf = io.BytesIO()
    PILImage.fromarray(arr, "RGB").save(buf, format="PNG")
    buf.seek(0)
    return (buf, name, "image/png")


def _wait_for_completion(client, analysis_id, auth_headers, max_polls=20):
    """Poll until analysis is completed or failed, or give up."""
    import time
    for _ in range(max_polls):
        r = client.get(f"/api/analysis/{analysis_id}", headers=auth_headers)
        status = r.get_json().get("analysis", {}).get("status", "")
        if status in ("completed", "failed"):
            return status
        time.sleep(0.3)
    return "timeout"


# ── Health endpoints ──────────────────────────────────────────────────────────

class TestHealthEndpoints:

    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert "app" in data

    def test_api_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_ready_endpoint(self, client):
        r = client.get("/ready")
        assert r.status_code in (200, 503)   # may not have all deps in test env
        data = r.get_json()
        assert "checks" in data
        assert "database" in data["checks"]

    def test_models_endpoint(self, client, auth_headers):
        r = client.get("/api/models", headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()
        assert "models" in data
        for model_key in ["blip", "blip_vqa", "grounding_dino", "change_detection"]:
            assert model_key in data["models"]


# ── Single image analysis ─────────────────────────────────────────────────────

class TestSingleImageAnalysis:

    def test_single_upload_success(self, client, auth_headers):
        r = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code in (200, 202), f"Got {r.status_code}: {r.get_json()}"
        data = r.get_json()
        assert data["success"] is True
        assert "analysis_id" in data

    def test_single_upload_with_nlq(self, client, auth_headers):
        r = client.post(
            "/api/analyze/single",
            data={"image": _png_file(), "nl_query": "What land cover is visible?"},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code in (200, 202)
        assert r.get_json()["success"] is True

    def test_single_no_image_returns_400(self, client, auth_headers):
        r = client.post(
            "/api/analyze/single",
            data={},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_single_wrong_filetype_rejected(self, client, auth_headers):
        fake_exe = (io.BytesIO(b"MZ\x90\x00"), "malware.exe", "application/octet-stream")
        r = client.post(
            "/api/analyze/single",
            data={"image": fake_exe},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert r.get_json()["success"] is False

    def test_single_requires_auth(self, client):
        r = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
        )
        assert r.status_code == 401

    def test_single_result_has_required_fields(self, client, auth_headers):
        r = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        data = r.get_json()
        analysis_id = data["analysis_id"]

        # If queued, wait for completion
        if data.get("queued"):
            _wait_for_completion(client, analysis_id, auth_headers)

        result_r = client.get(f"/api/analysis/{analysis_id}", headers=auth_headers)
        result_data = result_r.get_json().get("analysis", {}).get("result", {})

        if result_data:
            # Validate expected top-level keys exist
            for key in ["landcover", "water", "agriculture", "buildings", "confidence"]:
                assert key in result_data, f"Missing key in result: {key}"

    def test_result_contains_no_fabricated_buildings(self, client, auth_headers):
        """Building count must be None (not configured) — never a fake number."""
        r = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        data = r.get_json()
        if data.get("queued"):
            _wait_for_completion(client, data["analysis_id"], auth_headers)
        result_r = client.get(f"/api/analysis/{data['analysis_id']}", headers=auth_headers)
        result = result_r.get_json().get("analysis", {}).get("result", {})
        buildings = result.get("buildings", {})
        # Must be explicitly None or have a limitation — never a fabricated count
        assert buildings.get("building_count") is None or buildings.get("limitation")


# ── Multitemporal analysis ────────────────────────────────────────────────────

class TestMultitemporalAnalysis:

    def test_multitemporal_upload_success(self, client, auth_headers):
        r = client.post(
            "/api/analyze/multitemporal",
            data={
                "before_image": _png_file("before.png"),
                "after_image":  _png_file("after.png"),
                "before_date":  "2023-01-01",
                "after_date":   "2024-01-01",
            },
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code in (200, 202), f"Got {r.status_code}: {r.get_json()}"
        assert r.get_json()["success"] is True

    def test_multitemporal_missing_after_returns_400(self, client, auth_headers):
        r = client.post(
            "/api/analyze/multitemporal",
            data={"before_image": _png_file("before.png")},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_multitemporal_change_detection_runs(self, client, auth_headers):
        r = client.post(
            "/api/analyze/multitemporal",
            data={
                "before_image": _png_file("b.png"),
                "after_image":  _png_file("a.png"),
            },
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        data = r.get_json()
        if data.get("queued"):
            status = _wait_for_completion(client, data["analysis_id"], auth_headers)
            assert status in ("completed", "timeout")
        result_r = client.get(f"/api/analysis/{data['analysis_id']}", headers=auth_headers)
        result = result_r.get_json().get("analysis", {}).get("result", {})
        if result:
            # Change detection must be present for multitemporal
            assert "change_detection" in result


# ── History, retrieval, delete ────────────────────────────────────────────────

class TestHistoryAPI:

    def test_history_returns_list(self, client, auth_headers):
        r = client.get("/api/analysis/history", headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data.get("analyses"), list)
        assert isinstance(data.get("total"), int)

    def test_history_pagination(self, client, auth_headers):
        r = client.get("/api/analysis/history?page=1&per_page=5", headers=auth_headers)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["analyses"]) <= 5

    def test_history_is_user_scoped(self, client, auth_headers):
        # Second user should see empty history
        email2 = f"user2_{uuid.uuid4().hex[:6]}@test.local"
        client.post("/api/auth/register", json={
            "full_name": "User Two", "email": email2,
            "password": "SecondUser1", "confirm_password": "SecondUser1",
        })
        login2 = client.post("/api/auth/login", json={"email": email2, "password": "SecondUser1"})
        token2 = login2.get_json()["access_token"]
        r = client.get("/api/analysis/history",
                       headers={"Authorization": f"Bearer {token2}"})
        data = r.get_json()
        assert data["total"] == 0   # new user has no analyses

    def test_get_nonexistent_analysis_404(self, client, auth_headers):
        r = client.get(f"/api/analysis/{uuid.uuid4()}", headers=auth_headers)
        assert r.status_code == 404

    def test_get_other_users_analysis_404(self, client, auth_headers):
        """User cannot retrieve another user's analysis."""
        email3 = f"user3_{uuid.uuid4().hex[:6]}@test.local"
        client.post("/api/auth/register", json={
            "full_name": "User Three", "email": email3,
            "password": "ThirdUser1", "confirm_password": "ThirdUser1",
        })
        login3 = client.post("/api/auth/login", json={"email": email3, "password": "ThirdUser1"})
        token3 = login3.get_json()["access_token"]

        # Create an analysis as user3
        upload = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
            headers={"Authorization": f"Bearer {token3}"},
        )
        analysis_id = upload.get_json().get("analysis_id")
        if not analysis_id:
            pytest.skip("Upload failed — skipping cross-user test")

        # Main test user tries to access it — must get 404
        r = client.get(f"/api/analysis/{analysis_id}", headers=auth_headers)
        assert r.status_code == 404

    def test_delete_analysis(self, client, auth_headers):
        # Create one
        upload = client.post(
            "/api/analyze/single",
            data={"image": _png_file()},
            content_type="multipart/form-data",
            headers=auth_headers,
        )
        aid = upload.get_json().get("analysis_id")
        if not aid:
            pytest.skip("Upload failed")
        # Delete it
        del_r = client.delete(f"/api/analysis/{aid}", headers=auth_headers)
        assert del_r.status_code == 200
        # Verify gone
        get_r = client.get(f"/api/analysis/{aid}", headers=auth_headers)
        assert get_r.status_code == 404


# ── Coordinate analysis ───────────────────────────────────────────────────────

class TestCoordinateAnalysis:

    def test_valid_coordinates(self, client, auth_headers):
        r = client.post("/api/analyze/coordinates",
                        json={"latitude": 28.6, "longitude": 77.2, "mode": "single"},
                        headers=auth_headers)
        assert r.status_code in (200, 202)
        assert r.get_json()["success"] is True

    def test_invalid_latitude_rejected(self, client, auth_headers):
        r = client.post("/api/analyze/coordinates",
                        json={"latitude": 999, "longitude": 77.2, "mode": "single"},
                        headers=auth_headers)
        assert r.status_code == 422

    def test_invalid_longitude_rejected(self, client, auth_headers):
        r = client.post("/api/analyze/coordinates",
                        json={"latitude": 28.6, "longitude": -999, "mode": "single"},
                        headers=auth_headers)
        assert r.status_code == 422

    def test_missing_coordinates_rejected(self, client, auth_headers):
        r = client.post("/api/analyze/coordinates",
                        json={"mode": "single"},
                        headers=auth_headers)
        assert r.status_code == 422
