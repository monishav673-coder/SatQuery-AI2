"""
SATQUERY AI — Satellite Service Tests
Verifies coordinate validation, provider abstraction, and honest
no-imagery responses. Never fabricates satellite data.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import pytest


# ── Coordinate validation ─────────────────────────────────────────────────────

class TestCoordinateValidation:

    def test_valid_coordinates_pass(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(28.6, 77.2)
        assert not errors
        assert lat == 28.6
        assert lon == 77.2

    def test_latitude_above_90_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(91.0, 77.2)
        assert "latitude" in errors

    def test_latitude_below_minus_90_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(-91.0, 77.2)
        assert "latitude" in errors

    def test_longitude_above_180_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(28.6, 181.0)
        assert "longitude" in errors

    def test_longitude_below_minus_180_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(28.6, -181.0)
        assert "longitude" in errors

    def test_string_coordinate_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords("abc", 77.2)
        assert "latitude" in errors

    def test_none_coordinate_fails(self):
        from routes.coordinates import _validate_coords
        lat, lon, errors = _validate_coords(None, 77.2)
        assert "latitude" in errors

    def test_boundary_values_pass(self):
        from routes.coordinates import _validate_coords
        for lat, lon in [(-90, -180), (90, 180), (0, 0)]:
            _, _, errors = _validate_coords(lat, lon)
            assert not errors, f"Boundary ({lat},{lon}) should pass but got: {errors}"


# ── Satellite service — no provider configured ─────────────────────────────────

class TestSatelliteServiceNoProvider:
    """When SATELLITE_PROVIDER=none, returns honest unavailable response."""

    def setup_method(self):
        os.environ["SATELLITE_PROVIDER"] = "none"

    def test_returns_not_available(self, app):
        with app.app_context():
            from services.satellite_service import fetch_satellite_imagery
            result = fetch_satellite_imagery(lat=28.6, lon=77.2)
            assert result["available"] is False
            assert "not configured" in result["message"].lower() or \
                   "provider" in result["message"].lower()

    def test_does_not_fabricate_image(self, app):
        with app.app_context():
            from services.satellite_service import fetch_satellite_imagery
            result = fetch_satellite_imagery(lat=28.6, lon=77.2)
            # Must never return a fabricated thumbnail URL
            assert result.get("thumbnail_url") is None

    def test_returns_provider_none(self, app):
        with app.app_context():
            from services.satellite_service import fetch_satellite_imagery
            result = fetch_satellite_imagery(lat=0.0, lon=0.0)
            assert result.get("provider") == "none"


# ── Geocoding service ─────────────────────────────────────────────────────────

class TestGeocodingService:

    def test_reverse_geocode_returns_string_or_none(self, app):
        """Nominatim may be unavailable in CI — just check it doesn't crash."""
        with app.app_context():
            from services.geocoding_service import reverse_geocode
            result = reverse_geocode(28.6139, 77.2090)
            assert result is None or isinstance(result, str)

    def test_invalid_coords_does_not_crash(self, app):
        """Even with boundary coords, should not raise."""
        with app.app_context():
            from services.geocoding_service import reverse_geocode
            try:
                result = reverse_geocode(90.0, 180.0)
                assert result is None or isinstance(result, str)
            except Exception as e:
                pytest.fail(f"reverse_geocode raised unexpectedly: {e}")


# ── OTP service — provider not configured ─────────────────────────────────────

class TestOTPServiceNotConfigured:

    def setup_method(self):
        os.environ.pop("SMS_PROVIDER", None)

    def test_send_otp_returns_not_configured(self):
        from services.sms_service import send_otp
        result = send_otp("+919876543210", "123456")
        assert result["sent"] is False
        assert "not configured" in result["error"].lower()

    def test_otp_hash_is_not_plaintext(self):
        from services.sms_service import generate_otp, hash_otp
        otp  = generate_otp(6)
        salt = "test-salt"
        h    = hash_otp(otp, salt)
        assert otp not in h          # OTP not stored in hash
        assert len(h) == 64          # SHA-256 hex = 64 chars

    def test_verify_otp_correct(self):
        from services.sms_service import generate_otp, hash_otp, verify_otp_hash
        otp  = generate_otp(6)
        salt = "verify-salt"
        h    = hash_otp(otp, salt)
        assert verify_otp_hash(otp, salt, h) is True

    def test_verify_otp_wrong(self):
        from services.sms_service import generate_otp, hash_otp, verify_otp_hash
        otp  = generate_otp(6)
        salt = "verify-salt"
        h    = hash_otp(otp, salt)
        assert verify_otp_hash("999999", salt, h) is False

    def test_dev_otp_blocked_in_production(self):
        os.environ["SMS_PROVIDER"] = "development"
        os.environ["FLASK_ENV"]    = "production"
        from services.sms_service import send_otp
        # reimport to pick up env changes
        import importlib, services.sms_service as sms
        importlib.reload(sms)
        result = sms.send_otp("+911234567890", "111111")
        assert result["sent"] is False
        assert "misconfigured" in result["error"].lower() or "production" in result["error"].lower()
        # Cleanup
        os.environ.pop("SMS_PROVIDER", None)
        os.environ["FLASK_ENV"] = "testing"
