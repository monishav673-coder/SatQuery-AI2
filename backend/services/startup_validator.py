"""
SATQUERY AI — Startup Configuration Validator
Validates required and optional environment variables at application start.
Never crashes silently — all missing required variables are reported clearly.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import NamedTuple

logger = logging.getLogger(__name__)


class ConfigCheck(NamedTuple):
    key: str
    required: bool
    description: str
    redact: bool = False      # If True, value is not logged


CHECKS: list[ConfigCheck] = [
    # ── REQUIRED ─────────────────────────────────────────────────────────
    ConfigCheck("SECRET_KEY",         True,  "Flask secret key",              redact=True),
    ConfigCheck("JWT_SECRET_KEY",     True,  "JWT signing secret",            redact=True),
    # ── STRONGLY RECOMMENDED ─────────────────────────────────────────────
    ConfigCheck("DATABASE_URL",       False, "Database connection URL",       redact=True),
    ConfigCheck("REDIS_URL",          False, "Redis connection URL (async workers + SSE)"),
    ConfigCheck("CORS_ORIGINS",       False, "Allowed CORS origins"),
    # ── STORAGE ──────────────────────────────────────────────────────────
    ConfigCheck("UPLOAD_FOLDER",      False, "Path for uploaded images"),
    ConfigCheck("REPORTS_FOLDER",     False, "Path for generated PDF reports"),
    # ── ML MODELS (all optional) ──────────────────────────────────────────
    ConfigCheck("BLIP_ENABLED",           False, "Enable BLIP captioning model"),
    ConfigCheck("BLIP_VQA_ENABLED",       False, "Enable BLIP VQA model"),
    ConfigCheck("GROUNDING_DINO_ENABLED", False, "Enable Grounding DINO detection"),
    ConfigCheck("BIGEARTHNET_ENABLED",    False, "Enable BigEarthNet classifier"),
    ConfigCheck("BIGEARTHNET_MODEL_PATH", False, "Path to BigEarthNet model weights"),
    ConfigCheck("CHANGE_DETECTION_ENABLED",   False, "Enable change detection model"),
    ConfigCheck("CHANGE_DETECTION_MODEL_PATH",False, "Path to change detection weights"),
    ConfigCheck("SAR_ANALYSIS_ENABLED",   False, "Enable SAR analysis model"),
    ConfigCheck("SAR_MODEL_PATH",         False, "Path to SAR model weights"),
    # ── SATELLITE PROVIDER ────────────────────────────────────────────────
    ConfigCheck("SATELLITE_PROVIDER",         False, "Satellite imagery provider"),
    ConfigCheck("SENTINEL_HUB_CLIENT_ID",     False, "Sentinel Hub client ID",     redact=True),
    ConfigCheck("SENTINEL_HUB_CLIENT_SECRET", False, "Sentinel Hub client secret", redact=True),
    # ── SMS / OTP ─────────────────────────────────────────────────────────
    ConfigCheck("SMS_PROVIDER",        False, "SMS provider for OTP"),
    ConfigCheck("SMS_PROVIDER_API_KEY",False, "SMS provider API key",          redact=True),
    # ── GEOCODING ─────────────────────────────────────────────────────────
    ConfigCheck("GEOCODING_PROVIDER",  False, "Geocoding provider"),
    ConfigCheck("GOOGLE_MAPS_API_KEY", False, "Google Maps API key",           redact=True),
]

_DEFAULT_WEAK = {"change-me", "replace-with", "your-", "secret-key", "secret_key"}


def validate_startup(flask_env: str = "development") -> dict:
    """
    Run all config checks. Returns summary dict.
    In production, exits with code 1 if required vars are missing.
    """
    is_prod = flask_env.lower() == "production"
    missing_required: list[str] = []
    weak_secrets: list[str] = []
    configured: list[str] = []
    not_configured: list[str] = []

    lines = [
        "=" * 60,
        "  SATQUERY AI — Startup Configuration Check",
        f"  Environment: {flask_env.upper()}",
        "=" * 60,
    ]

    for check in CHECKS:
        val = os.environ.get(check.key, "").strip()
        display = ("***" if check.redact else val) if val else "<not set>"

        if val:
            configured.append(check.key)
            # Warn on weak secrets
            if check.redact and any(w in val.lower() for w in _DEFAULT_WEAK):
                weak_secrets.append(check.key)
                lines.append(f"  ⚠  {check.key:40s} = {display}  [WEAK — change before deploying]")
            else:
                lines.append(f"  ✓  {check.key:40s} = {display}")
        else:
            not_configured.append(check.key)
            if check.required:
                missing_required.append(check.key)
                lines.append(f"  ✗  {check.key:40s} = <MISSING — REQUIRED>")
            else:
                lines.append(f"  ○  {check.key:40s} = <not configured>  [{check.description}]")

    lines.append("=" * 60)

    # Model availability summary
    model_flags = {
        "BLIP":             os.environ.get("BLIP_ENABLED", "").lower() == "true",
        "BLIP VQA":         os.environ.get("BLIP_VQA_ENABLED", "").lower() == "true",
        "Grounding DINO":   os.environ.get("GROUNDING_DINO_ENABLED", "").lower() == "true",
        "BigEarthNet":      os.environ.get("BIGEARTHNET_ENABLED", "").lower() == "true",
        "Change Detection": os.environ.get("CHANGE_DETECTION_ENABLED", "").lower() == "true",
        "SAR Analysis":     os.environ.get("SAR_ANALYSIS_ENABLED", "").lower() == "true",
    }
    lines.append("  Model Configuration:")
    for name, enabled in model_flags.items():
        lines.append(f"    {'✓' if enabled else '○'}  {name}: {'ENABLED' if enabled else 'NOT CONFIGURED'}")
    lines.append("=" * 60)

    summary_text = "\n".join(lines)
    logger.info("\n%s", summary_text)

    result = {
        "env": flask_env,
        "configured": configured,
        "not_configured": not_configured,
        "missing_required": missing_required,
        "weak_secrets": weak_secrets,
        "models": model_flags,
        "ok": len(missing_required) == 0,
    }

    if missing_required:
        msg = (
            f"SATQUERY AI startup failed: required environment variable(s) missing: "
            f"{', '.join(missing_required)}. "
            "Set them in .env or your container environment."
        )
        if is_prod:
            logger.critical(msg)
            sys.exit(1)
        else:
            logger.warning(msg)

    if weak_secrets and is_prod:
        logger.warning(
            "SECURITY WARNING: weak secret value(s) detected in production: %s. "
            "Replace before deploying.",
            weak_secrets,
        )

    return result
