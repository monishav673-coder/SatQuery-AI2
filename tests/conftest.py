"""
SATQUERY AI — Shared pytest fixtures
Provides: app, client, db_session, auth_token, test_image_path
"""

from __future__ import annotations

import io
import os
import sys
import uuid

import pytest
from PIL import Image as PILImage
import numpy as np

# ── Make backend importable ───────────────────────────────────────────────────
_backend = os.path.join(os.path.dirname(__file__), "..", "backend")
_root    = os.path.join(os.path.dirname(__file__), "..")
for p in (_backend, _root):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SECRET_KEY",     "test-secret-key-not-for-production")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-not-for-production")
os.environ.setdefault("DATABASE_URL",   "sqlite:///:memory:")
os.environ.setdefault("UPLOAD_FOLDER",  "/tmp/satquery_test_uploads")
os.environ.setdefault("REPORTS_FOLDER", "/tmp/satquery_test_reports")
os.environ.setdefault("CHANGE_DETECTION_ENABLED", "true")
os.environ.setdefault("BLIP_ENABLED",           "false")
os.environ.setdefault("BLIP_VQA_ENABLED",       "false")
os.environ.setdefault("GROUNDING_DINO_ENABLED",  "false")
os.environ.setdefault("BIGEARTHNET_ENABLED",     "false")
os.environ.setdefault("SAR_ANALYSIS_ENABLED",    "false")

# Create app once at module level to avoid duplicate endpoint registration
# when pytest session fixture is called multiple times across test modules.
_APP = None

def _get_app():
    global _APP
    if _APP is None:
        from app import create_app
        _APP = create_app()
        _APP.config["TESTING"] = True
        _APP.config["WTF_CSRF_ENABLED"] = False
        os.makedirs(_APP.config["UPLOAD_FOLDER"],  exist_ok=True)
        os.makedirs(_APP.config["REPORTS_FOLDER"], exist_ok=True)
    return _APP


@pytest.fixture(scope="session")
def app():
    return _get_app()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def db_session(app):
    with app.app_context():
        from database.models import db
        yield db.session


# ── User / auth helpers ───────────────────────────────────────────────────────

_TEST_EMAIL    = f"test_{uuid.uuid4().hex[:6]}@satquery.test"
_TEST_PASSWORD = "TestPass123"
_TEST_NAME     = "Test User"
_auth_token: str | None = None


@pytest.fixture(scope="session")
def registered_user(client):
    """Register once per test session."""
    resp = client.post("/api/auth/register", json={
        "full_name":          _TEST_NAME,
        "email":              _TEST_EMAIL,
        "password":           _TEST_PASSWORD,
        "confirm_password":   _TEST_PASSWORD,
        "preferred_language": "en",
    })
    assert resp.status_code in (201, 409), f"Register failed: {resp.get_json()}"
    return {"email": _TEST_EMAIL, "password": _TEST_PASSWORD}


@pytest.fixture(scope="session")
def auth_token(client, registered_user):
    """Login and return the JWT access token."""
    global _auth_token
    if _auth_token:
        return _auth_token
    resp = client.post("/api/auth/login", json={
        "email":    registered_user["email"],
        "password": registered_user["password"],
    })
    data = resp.get_json()
    assert resp.status_code == 200, f"Login failed: {data}"
    _auth_token = data["access_token"]
    return _auth_token


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── Test image fixtures ───────────────────────────────────────────────────────

def _make_test_png(w: int = 100, h: int = 100) -> bytes:
    """Create a synthetic 100×100 RGB satellite-like PNG in memory."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:h//2, :w//2]   = [20,  40, 120]   # dark blue  — water proxy
    arr[:h//2, w//2:]   = [40, 120,  40]   # green      — vegetation proxy
    arr[h//2:, :w//2]   = [180,150, 100]   # tan        — bare land proxy
    arr[h//2:, w//2:]   = [130,130, 130]   # grey       — urban proxy
    buf = io.BytesIO()
    PILImage.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="session")
def test_image_bytes():
    return _make_test_png()


@pytest.fixture(scope="session")
def test_image_path(tmp_path_factory):
    d = tmp_path_factory.mktemp("images")
    path = d / "test_satellite.png"
    path.write_bytes(_make_test_png())
    return str(path)


@pytest.fixture(scope="session")
def test_image_before_path(tmp_path_factory):
    d = tmp_path_factory.mktemp("temporal")
    path = d / "before.png"
    path.write_bytes(_make_test_png(100, 100))
    return str(path)


@pytest.fixture(scope="session")
def test_image_after_path(tmp_path_factory):
    d = tmp_path_factory.mktemp("temporal")
    path = d / "after.png"
    # Slightly different from before to trigger change detection
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[:50, :50] = [200, 200, 200]   # brighter — simulates construction
    arr[50:, 50:] = [10,  60, 100]    # darker   — simulates water expansion
    buf = io.BytesIO()
    PILImage.fromarray(arr, "RGB").save(buf, format="PNG")
    path.write_bytes(buf.getvalue())
    return str(path)
