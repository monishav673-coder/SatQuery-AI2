"""
SATQUERY AI — SMS / OTP Service Abstraction
Supports: Twilio, Fast2SMS, MSG91, TextLocal, or any HTTP-based SMS provider.

If SMS_PROVIDER is not set, every send attempt returns:
  {"sent": False, "error": "OTP service is not configured."}
  — never pretends the OTP was sent.

Development override (FLASK_ENV=development only):
  Set SMS_PROVIDER=development and the OTP is printed to server logs.
  This MUST NOT reach production — startup validator blocks it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_NEVER_LOG = {"otp", "code", "password", "secret", "token", "key"}


def _safe(v: str) -> str:
    return "***" if v else ""


# ── OTP generation ─────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically random numeric OTP."""
    return "".join(random.SystemRandom().choices(string.digits, k=length))


def hash_otp(otp: str, salt: str) -> str:
    """HMAC-SHA256 hash of the OTP — never store the plaintext OTP."""
    secret = os.environ.get("SECRET_KEY", "fallback-secret").encode()
    return hmac.new(secret, f"{salt}:{otp}".encode(), hashlib.sha256).hexdigest()


def verify_otp_hash(otp: str, salt: str, stored_hash: str) -> bool:
    expected = hash_otp(otp, salt)
    return hmac.compare_digest(expected, stored_hash)


# ── SMS providers ──────────────────────────────────────────────────────────────

def send_otp(mobile: str, otp: str) -> dict:
    """
    Send OTP via the configured SMS provider.
    Returns {"sent": True, "provider_ref": "..."} or {"sent": False, "error": "..."}.
    NEVER logs the OTP value.
    """
    provider = os.environ.get("SMS_PROVIDER", "").strip().lower()

    if not provider:
        return {"sent": False, "error": "OTP service is not configured. Set SMS_PROVIDER in .env."}

    flask_env = os.environ.get("FLASK_ENV", "production").lower()
    if provider == "development":
        if flask_env == "production":
            logger.error("SMS_PROVIDER=development is NOT allowed in production. OTP not sent.")
            return {"sent": False, "error": "OTP service misconfigured for production environment."}
        logger.warning(
            "DEVELOPMENT OTP MODE: OTP for %s has been generated. "
            "Check application logs — this mode is disabled in production.",
            _mask_mobile(mobile),
        )
        # Print OTP to stderr only — NEVER to a response or JSON
        print(f"\n[DEV OTP] Mobile: {mobile} | OTP: {otp}\n", flush=True)  # noqa: T201
        return {"sent": True, "provider_ref": "dev-mode"}

    if provider == "twilio":
        return _send_twilio(mobile, otp)
    if provider in ("fast2sms", "fast2"):
        return _send_fast2sms(mobile, otp)
    if provider == "msg91":
        return _send_msg91(mobile, otp)
    if provider == "textlocal":
        return _send_textlocal(mobile, otp)

    return {"sent": False, "error": f"Unknown SMS provider: {provider!r}. Check SMS_PROVIDER in .env."}


def _send_twilio(mobile: str, otp: str) -> dict:
    try:
        from twilio.rest import Client
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token  = os.environ.get("TWILIO_AUTH_TOKEN",  "")
        from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        if not all([account_sid, auth_token, from_number]):
            return {"sent": False, "error": "Twilio credentials not fully configured."}
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            body=f"Your SATQUERY AI verification code is: {otp}. Valid for {os.environ.get('OTP_EXPIRY_MINUTES', 10)} minutes.",
            from_=from_number,
            to=mobile,
        )
        logger.info("Twilio OTP sent to %s (sid=%s)", _mask_mobile(mobile), msg.sid)
        return {"sent": True, "provider_ref": msg.sid}
    except ImportError:
        return {"sent": False, "error": "twilio package not installed. pip install twilio"}
    except Exception as exc:
        logger.error("Twilio send failed for %s: %s", _mask_mobile(mobile), exc)
        return {"sent": False, "error": f"Twilio send failed: {exc}"}


def _send_fast2sms(mobile: str, otp: str) -> dict:
    try:
        import requests
        api_key = os.environ.get("SMS_PROVIDER_API_KEY", "")
        if not api_key:
            return {"sent": False, "error": "Fast2SMS API key not configured."}
        sender = os.environ.get("SMS_SENDER_ID", "SATQRY")
        resp = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            headers={"authorization": api_key, "Content-Type": "application/json"},
            json={
                "route": "otp",
                "variables_values": otp,
                "numbers": mobile.lstrip("+91"),
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("return"):
            ref = data.get("request_id", "")
            logger.info("Fast2SMS OTP sent to %s (ref=%s)", _mask_mobile(mobile), ref)
            return {"sent": True, "provider_ref": ref}
        return {"sent": False, "error": data.get("message", "Fast2SMS send failed.")}
    except Exception as exc:
        logger.error("Fast2SMS send failed for %s: %s", _mask_mobile(mobile), exc)
        return {"sent": False, "error": str(exc)}


def _send_msg91(mobile: str, otp: str) -> dict:
    try:
        import requests
        auth_key  = os.environ.get("SMS_PROVIDER_API_KEY", "")
        template  = os.environ.get("MSG91_TEMPLATE_ID",   "")
        sender    = os.environ.get("SMS_SENDER_ID", "SATQRY")
        if not auth_key:
            return {"sent": False, "error": "MSG91 auth key not configured."}
        resp = requests.post(
            "https://api.msg91.com/api/v5/otp",
            headers={"authkey": auth_key, "Content-Type": "application/json"},
            json={
                "template_id": template,
                "mobile":      mobile,
                "otp":         otp,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("type") == "success":
            logger.info("MSG91 OTP sent to %s", _mask_mobile(mobile))
            return {"sent": True, "provider_ref": data.get("request_id", "")}
        return {"sent": False, "error": data.get("message", "MSG91 send failed.")}
    except Exception as exc:
        logger.error("MSG91 send failed: %s", exc)
        return {"sent": False, "error": str(exc)}


def _send_textlocal(mobile: str, otp: str) -> dict:
    try:
        import requests
        api_key = os.environ.get("SMS_PROVIDER_API_KEY", "")
        sender  = os.environ.get("SMS_SENDER_ID", "SATQRY")
        if not api_key:
            return {"sent": False, "error": "TextLocal API key not configured."}
        resp = requests.post(
            "https://api.txtlocal.com/send/",
            data={
                "apikey":  api_key,
                "numbers": mobile,
                "message": f"Your SATQUERY AI OTP: {otp}. Valid 10 mins.",
                "sender":  sender,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") == "success":
            batch_id = data.get("batch_id", "")
            logger.info("TextLocal OTP sent to %s (batch=%s)", _mask_mobile(mobile), batch_id)
            return {"sent": True, "provider_ref": str(batch_id)}
        return {"sent": False, "error": str(data.get("errors", "TextLocal send failed."))}
    except Exception as exc:
        logger.error("TextLocal send failed: %s", exc)
        return {"sent": False, "error": str(exc)}


def _mask_mobile(mobile: str) -> str:
    if len(mobile) >= 6:
        return mobile[:3] + "***" + mobile[-3:]
    return "***"
