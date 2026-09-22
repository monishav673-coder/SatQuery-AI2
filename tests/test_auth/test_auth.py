"""
SATQUERY AI — Authentication Tests
Covers: registration, login, JWT guards, password hashing, OTP flow.
"""

import uuid
import pytest


# ── Registration ──────────────────────────────────────────────────────────────

class TestRegistration:

    def test_register_success(self, client):
        email = f"reg_{uuid.uuid4().hex[:8]}@test.local"
        resp  = client.post("/api/auth/register", json={
            "full_name": "Alice Tester", "email": email,
            "password": "ValidPass1", "confirm_password": "ValidPass1",
        })
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True

    def test_register_duplicate_email(self, client, registered_user):
        resp = client.post("/api/auth/register", json={
            "full_name": "Dup", "email": registered_user["email"],
            "password": "ValidPass1", "confirm_password": "ValidPass1",
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["success"] is False
        assert "email" in data.get("errors", {})

    def test_register_invalid_email(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "X", "email": "not-an-email",
            "password": "ValidPass1", "confirm_password": "ValidPass1",
        })
        assert resp.status_code == 422
        assert "email" in resp.get_json().get("errors", {})

    def test_register_weak_password(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "Y", "email": f"weak_{uuid.uuid4().hex[:6]}@test.local",
            "password": "short", "confirm_password": "short",
        })
        assert resp.status_code == 422
        assert "password" in resp.get_json().get("errors", {})

    def test_register_password_no_number(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "Y", "email": f"nonnum_{uuid.uuid4().hex[:6]}@test.local",
            "password": "NoNumbersHere", "confirm_password": "NoNumbersHere",
        })
        assert resp.status_code == 422

    def test_register_passwords_mismatch(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "Z", "email": f"mismatch_{uuid.uuid4().hex[:6]}@test.local",
            "password": "ValidPass1", "confirm_password": "Different1",
        })
        assert resp.status_code == 422
        assert "confirm_password" in resp.get_json().get("errors", {})

    def test_register_missing_name(self, client):
        resp = client.post("/api/auth/register", json={
            "full_name": "", "email": f"noname_{uuid.uuid4().hex[:6]}@test.local",
            "password": "ValidPass1", "confirm_password": "ValidPass1",
        })
        assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

class TestLogin:

    def test_login_success(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "email":    registered_user["email"],
            "password": registered_user["password"],
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert "access_token" in data
        assert len(data["access_token"]) > 20

    def test_login_wrong_password(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "email": registered_user["email"], "password": "WrongPassword9",
        })
        assert resp.status_code == 401
        assert resp.get_json()["success"] is False

    def test_login_nonexistent_email(self, client):
        resp = client.post("/api/auth/login", json={
            "email": "nobody@nothere.invalid", "password": "SomePass1",
        })
        assert resp.status_code == 401

    def test_login_empty_password(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "email": registered_user["email"], "password": "",
        })
        assert resp.status_code == 422

    def test_login_returns_user_info(self, client, registered_user):
        resp = client.post("/api/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"],
        })
        data = resp.get_json()
        assert "user" in data
        # Never return password hash
        assert "password" not in str(data["user"])
        assert "hash" not in str(data["user"])


# ── JWT guards ────────────────────────────────────────────────────────────────

class TestJWTGuards:

    def test_protected_requires_token(self, client):
        for endpoint in ["/api/auth/me", "/api/analysis/history"]:
            resp = client.get(endpoint)
            assert resp.status_code == 401, f"{endpoint} should require auth"

    def test_protected_accepts_valid_token(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_invalid_token_rejected(self, client):
        resp = client.get("/api/auth/me",
                          headers={"Authorization": "Bearer this.is.invalid"})
        assert resp.status_code == 422

    def test_malformed_bearer_rejected(self, client):
        resp = client.get("/api/auth/me",
                          headers={"Authorization": "NotBearer token"})
        assert resp.status_code == 401


# ── Password hashing — verify bcrypt is used, not plaintext ──────────────────

class TestPasswordSecurity:

    def test_password_is_hashed(self, app, registered_user):
        with app.app_context():
            from database.models import User
            user = User.query.filter_by(email=registered_user["email"]).first()
            assert user is not None
            # Hash must not contain the plaintext password
            assert registered_user["password"] not in user.password_hash
            # bcrypt hashes start with $2b$
            assert user.password_hash.startswith("$2b$") or user.password_hash.startswith("$2a$")

    def test_different_hashes_for_same_password(self, app, registered_user):
        """bcrypt uses per-hash salts — same password → different hashes."""
        with app.app_context():
            from routes.auth import _hash_password
            h1 = _hash_password("SamePassword1")
            h2 = _hash_password("SamePassword1")
            assert h1 != h2   # salts differ


# ── Profile update ────────────────────────────────────────────────────────────

class TestProfileUpdate:

    def test_update_name(self, client, auth_headers):
        resp = client.put("/api/auth/profile",
                          json={"full_name": "Updated Name"},
                          headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["user"]["full_name"] == "Updated Name"

    def test_update_language(self, client, auth_headers):
        resp = client.put("/api/auth/profile",
                          json={"preferred_language": "hi"},
                          headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()["user"]["preferred_language"] == "hi"

    def test_change_password_wrong_current(self, client, auth_headers):
        resp = client.put("/api/auth/profile",
                          json={"current_password": "WrongCurrent1",
                                "new_password":     "NewPass123"},
                          headers=auth_headers)
        assert resp.status_code == 422
        assert "current_password" in resp.get_json().get("errors", {})


# ── Logout ─────────────────────────────────────────────────────────────────────

class TestLogout:

    def test_logout_success(self, client, registered_user):
        # Get a fresh token
        login = client.post("/api/auth/login", json={
            "email": registered_user["email"], "password": registered_user["password"],
        })
        token = login.get_json()["access_token"]
        resp = client.post("/api/auth/logout",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_logout_requires_auth(self, client):
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401
