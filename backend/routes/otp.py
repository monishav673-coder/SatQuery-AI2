"""
SATQUERY AI — OTP / Forgot-Password Routes

POST /api/auth/forgot-password   — send OTP to mobile
POST /api/auth/verify-otp        — verify OTP
POST /api/auth/reset-password    — set new password with verified OTP

Flow:
  1. User submits email + mobile number
  2. System looks up user, validates mobile
  3. OTP generated, hashed, stored in otp_requests table
  4. SMS sent via configured provider (or returns not-configured error)
  5. User submits OTP → verified against hash
  6. If valid: user submits new password → updated

Security:
  - OTP is hashed with HMAC-SHA256, never stored plaintext
  - Max 5 attempts per OTP token
  - OTP expires after OTP_EXPIRY_MINUTES (default 10)
  - Rate limiting applied (5 requests/minute per IP)
  - Reset tokens are single-use
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app
from flask_bcrypt import Bcrypt

from database.models import db, User, OTPRequest, AuditLog
from services.sms_service import generate_otp, hash_otp, verify_otp_hash, send_otp

otp_bp  = Blueprint("otp", __name__)
_bcrypt = Bcrypt()

MOBILE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")


def _log(event: str, user_id: str = None, success: bool = True, detail: str = None):
    try:
        entry = AuditLog(
            user_id=user_id,
            event=event,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:256],
            detail=detail,
            success=success,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass  # audit log failure must not break the request


# ── Step 1: Request OTP ────────────────────────────────────────────────────────

@otp_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data   = request.get_json(silent=True) or {}
    email  = (data.get("email") or "").strip().lower()
    mobile = (data.get("mobile") or "").strip()

    errors = {}
    if not email:
        errors["email"] = "Email is required."
    if not mobile:
        errors["mobile"] = "Mobile number is required."
    elif not MOBILE_RE.match(mobile):
        errors["mobile"] = "Enter a valid international mobile number (e.g. +919876543210)."
    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    user = User.query.filter_by(email=email, is_active=True).first()
    # Deliberate vague response — do not confirm if email exists
    if not user:
        return jsonify({
            "success": True,
            "message": "If this email is registered, an OTP has been sent to the provided mobile number.",
        }), 200

    # Check stored mobile matches (if user has one)
    if user.mobile_number and user.mobile_number != mobile:
        _log("otp_request_mobile_mismatch", user.id, False)
        return jsonify({
            "success": True,
            "message": "If this email is registered, an OTP has been sent to the provided mobile number.",
        }), 200

    # Generate OTP
    otp     = generate_otp(6)
    salt    = uuid.uuid4().hex
    otp_h   = hash_otp(otp, salt)
    expiry  = datetime.utcnow() + timedelta(minutes=current_app.config.get("OTP_EXPIRY_MINUTES", 10))

    # Invalidate previous pending OTPs for this user
    OTPRequest.query.filter_by(user_id=user.id, used=False).update({"used": True})

    otp_record = OTPRequest(
        user_id=user.id,
        mobile_number=mobile,
        otp_hash=f"{salt}:{otp_h}",   # store salt alongside hash
        expires_at=expiry,
    )
    db.session.add(otp_record)

    # Update mobile on user record if not set
    if not user.mobile_number:
        user.mobile_number = mobile
    db.session.commit()

    # Send OTP — if provider not configured, return honest error
    result = send_otp(mobile, otp)
    if not result.get("sent"):
        _log("otp_send_failed", user.id, False, result.get("error"))
        return jsonify({
            "success": False,
            "error": result.get("error", "OTP service is not configured."),
        }), 503

    otp_record.provider_ref = result.get("provider_ref")
    db.session.commit()

    _log("otp_sent", user.id, True)
    return jsonify({
        "success": True,
        "otp_request_id": otp_record.id,
        "message": "OTP sent to your mobile number. Valid for "
                   f"{current_app.config.get('OTP_EXPIRY_MINUTES', 10)} minutes.",
        "expires_at": expiry.isoformat(),
    }), 200


# ── Step 2: Verify OTP ─────────────────────────────────────────────────────────

@otp_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data           = request.get_json(silent=True) or {}
    otp_request_id = (data.get("otp_request_id") or "").strip()
    submitted_otp  = (data.get("otp") or "").strip()

    if not otp_request_id or not submitted_otp:
        return jsonify({"success": False, "error": "otp_request_id and otp are required."}), 422

    record = db.session.get(OTPRequest, otp_request_id)
    if not record:
        return jsonify({"success": False, "error": "Invalid or expired OTP request."}), 400

    # Increment attempts immediately to prevent brute force
    record.attempts += 1
    db.session.commit()

    if not record.is_valid():
        _log("otp_verify_invalid", record.user_id, False,
             "expired" if record.is_expired() else f"attempts={record.attempts}")
        return jsonify({
            "success": False,
            "error": "OTP has expired or is no longer valid. Please request a new one.",
        }), 400

    # Verify hash
    try:
        salt, stored_hash = record.otp_hash.split(":", 1)
    except ValueError:
        return jsonify({"success": False, "error": "OTP record is malformed."}), 500

    if not verify_otp_hash(submitted_otp, salt, stored_hash):
        remaining = max(0, 5 - record.attempts)
        _log("otp_verify_wrong", record.user_id, False)
        return jsonify({
            "success": False,
            "error": f"Incorrect OTP. {remaining} attempt(s) remaining.",
        }), 400

    # OTP correct — issue a single-use reset token (not the OTP itself)
    reset_token = uuid.uuid4().hex + uuid.uuid4().hex   # 64-char random token
    reset_token_hash = hash_otp(reset_token, salt)
    record.otp_hash = f"{salt}:{reset_token_hash}"      # repurpose field for reset token
    record.used     = False                              # will be marked used on reset
    db.session.commit()

    _log("otp_verify_success", record.user_id, True)
    return jsonify({
        "success": True,
        "reset_token": reset_token,
        "otp_request_id": otp_request_id,
        "message": "OTP verified. Use the reset_token to set a new password.",
    }), 200


# ── Step 3: Reset Password ─────────────────────────────────────────────────────

@otp_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data           = request.get_json(silent=True) or {}
    otp_request_id = (data.get("otp_request_id") or "").strip()
    reset_token    = (data.get("reset_token") or "").strip()
    new_password   = data.get("new_password") or ""

    if not otp_request_id or not reset_token or not new_password:
        return jsonify({
            "success": False,
            "error": "otp_request_id, reset_token and new_password are required.",
        }), 422

    # Validate password strength
    from routes.auth import _validate_password
    pw_err = _validate_password(new_password)
    if pw_err:
        return jsonify({"success": False, "errors": {"new_password": pw_err}}), 422

    record = db.session.get(OTPRequest, otp_request_id)
    if not record or record.used or record.is_expired():
        return jsonify({"success": False, "error": "Reset token is invalid or has expired."}), 400

    # Verify reset token
    try:
        salt, stored_hash = record.otp_hash.split(":", 1)
    except ValueError:
        return jsonify({"success": False, "error": "Reset record is malformed."}), 500

    if not verify_otp_hash(reset_token, salt, stored_hash):
        _log("password_reset_bad_token", record.user_id, False)
        return jsonify({"success": False, "error": "Invalid reset token."}), 400

    user = db.session.get(User, record.user_id)
    if not user or not user.is_active:
        return jsonify({"success": False, "error": "User account not found or inactive."}), 404

    # Hash and update password — NEVER log the password
    from routes.auth import _hash_password
    user.password_hash = _hash_password(new_password)

    # Consume the reset record
    record.used = True
    db.session.commit()

    _log("password_reset_success", user.id, True)
    return jsonify({
        "success": True,
        "message": "Password updated successfully. Please log in with your new password.",
    }), 200
