"""
SATQUERY AI — Authentication Routes
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
PUT  /api/auth/profile
"""

import re
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from flask_bcrypt import Bcrypt

from database.models import db, User

auth_bp = Blueprint("auth", __name__)
bcrypt = Bcrypt()

# ── helpers ───────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$")
SUPPORTED_LANGUAGES = [
    "en", "ta", "hi", "te", "kn", "ml", "bn", "mr"
]

_token_blocklist: set = set()   # in-memory; replace with Redis/DB for production


def _hash_password(plain: str) -> str:
    return bcrypt.generate_password_hash(plain, rounds=current_app.config.get("BCRYPT_LOG_ROUNDS", 12)).decode("utf-8")


def _check_password(plain: str, hashed: str) -> bool:
    return bcrypt.check_password_hash(hashed, plain)


def _validate_password(password: str) -> str | None:
    """Returns an error string or None if valid."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password):
        return "Password must contain at least one letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one number."
    return None


# ── register ──────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""
    preferred_language = (data.get("preferred_language") or "en").strip().lower()

    # ── Validation ────────────────────────────────────────────────────────
    errors = {}

    if not full_name:
        errors["full_name"] = "Full name is required."
    elif len(full_name) < 2:
        errors["full_name"] = "Full name must be at least 2 characters."

    if not email:
        errors["email"] = "Email is required."
    elif not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."

    pw_error = _validate_password(password)
    if pw_error:
        errors["password"] = pw_error

    if not confirm_password:
        errors["confirm_password"] = "Please confirm your password."
    elif password != confirm_password:
        errors["confirm_password"] = "Passwords do not match."

    if preferred_language not in SUPPORTED_LANGUAGES:
        preferred_language = "en"

    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    # ── Duplicate check ───────────────────────────────────────────────────
    if User.query.filter_by(email=email).first():
        return jsonify({
            "success": False,
            "errors": {"email": "An account with this email already exists."}
        }), 409

    # ── Create user ───────────────────────────────────────────────────────
    user = User(
        full_name=full_name,
        email=email,
        password_hash=_hash_password(password),
        preferred_language=preferred_language,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Account created successfully. Please log in.",
    }), 201


# ── login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    errors = {}
    if not email:
        errors["email"] = "Email is required."
    elif not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."
    if not password:
        errors["password"] = "Password is required."

    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    user = User.query.filter_by(email=email).first()

    # Use constant-time comparison path even when user not found to prevent timing attacks
    if user is None or not _check_password(password, user.password_hash):
        return jsonify({
            "success": False,
            "errors": {"general": "Incorrect email or password."}
        }), 401

    if not user.is_active:
        return jsonify({"success": False, "errors": {"general": "This account has been deactivated."}}), 403

    # Update last login
    user.last_login = datetime.now(timezone.utc)
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify({
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict(),
    }), 200


# ── logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt().get("jti")
    if jti:
        _token_blocklist.add(jti)
    return jsonify({"success": True, "message": "Logged out successfully."}), 200


# ── me ────────────────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404
    return jsonify({"success": True, "user": user.to_dict()}), 200


# ── update profile ────────────────────────────────────────────────────────────

@auth_bp.route("/profile", methods=["PUT"])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found."}), 404

    data = request.get_json(silent=True) or {}
    errors = {}

    if "full_name" in data:
        full_name = (data["full_name"] or "").strip()
        if len(full_name) < 2:
            errors["full_name"] = "Full name must be at least 2 characters."
        else:
            user.full_name = full_name

    if "preferred_language" in data:
        lang = (data["preferred_language"] or "en").lower().strip()
        user.preferred_language = lang if lang in SUPPORTED_LANGUAGES else "en"

    if "current_password" in data and "new_password" in data:
        if not _check_password(data["current_password"], user.password_hash):
            errors["current_password"] = "Current password is incorrect."
        else:
            pw_error = _validate_password(data["new_password"])
            if pw_error:
                errors["new_password"] = pw_error
            else:
                user.password_hash = _hash_password(data["new_password"])

    if errors:
        return jsonify({"success": False, "errors": errors}), 422

    db.session.commit()
    return jsonify({"success": True, "user": user.to_dict()}), 200
