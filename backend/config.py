"""
SATQUERY AI — Configuration Module
All application configuration in one place with environment-variable support.
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


class Config:
    # ── Core ──────────────────────────────────────────────────────────────────
    SECRET_KEY  = os.environ.get("SECRET_KEY",  "change-me-in-production-use-a-long-random-string")
    DEBUG       = _bool("DEBUG", False)
    APP_NAME    = "SATQUERY AI"
    APP_VERSION = "2.0.0"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(BASE_DIR, 'database', 'satquery.db')}",
    )
    SQLALCHEMY_DATABASE_URI    = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS  = {"pool_pre_ping": True}

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY             = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES   = timedelta(hours=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) // 60 or 24)
    JWT_REFRESH_TOKEN_EXPIRES  = timedelta(days=30)

    # ── File upload ───────────────────────────────────────────────────────────
    UPLOAD_FOLDER      = os.environ.get("UPLOAD_FOLDER",  os.path.join(BASE_DIR, "uploads"))
    REPORTS_FOLDER     = os.environ.get("REPORTS_FOLDER", os.path.join(BASE_DIR, "uploads", "reports"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "100")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "tif", "tiff"}

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS = os.environ.get(
        "CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
    ).split(",")

    # ── Rate limiting (flask-limiter) ─────────────────────────────────────────
    RATELIMIT_STORAGE_URI     = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT         = os.environ.get("RATELIMIT_DEFAULT", "200 per minute")
    LOGIN_RATE_LIMIT          = os.environ.get("LOGIN_RATE_LIMIT", "10 per minute")
    REGISTER_RATE_LIMIT       = os.environ.get("REGISTER_RATE_LIMIT", "5 per minute")

    # ── Security headers ──────────────────────────────────────────────────────
    SEND_SECURITY_HEADERS = _bool("SEND_SECURITY_HEADERS", True)

    # ── Geocoding ─────────────────────────────────────────────────────────────
    GEOCODING_PROVIDER  = os.environ.get("GEOCODING_PROVIDER", "nominatim")
    GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    # ── Satellite provider ────────────────────────────────────────────────────
    SATELLITE_PROVIDER          = os.environ.get("SATELLITE_PROVIDER", "none")
    SENTINEL_HUB_CLIENT_ID      = os.environ.get("SENTINEL_HUB_CLIENT_ID", "")
    SENTINEL_HUB_CLIENT_SECRET  = os.environ.get("SENTINEL_HUB_CLIENT_SECRET", "")
    USGS_EE_USERNAME            = os.environ.get("USGS_EE_USERNAME", "")
    USGS_EE_PASSWORD            = os.environ.get("USGS_EE_PASSWORD", "")

    # ── ML models ─────────────────────────────────────────────────────────────
    MODEL_DEVICE    = os.environ.get("MODEL_DEVICE", "cpu")
    MODEL_CACHE_DIR = os.environ.get("MODEL_CACHE_DIR", os.path.join(BASE_DIR, ".model_cache"))

    BLIP_ENABLED                   = _bool("BLIP_ENABLED", False)
    BLIP_VQA_ENABLED               = _bool("BLIP_VQA_ENABLED", False)
    GROUNDING_DINO_ENABLED         = _bool("GROUNDING_DINO_ENABLED", False)
    GROUNDING_DINO_WEIGHTS_PATH    = os.environ.get("GROUNDING_DINO_WEIGHTS_PATH", "")
    GROUNDING_DINO_CONFIG_PATH     = os.environ.get("GROUNDING_DINO_CONFIG_PATH", "")

    BIGEARTHNET_ENABLED            = _bool("BIGEARTHNET_ENABLED", False)
    BIGEARTHNET_DATASET_PATH       = os.environ.get("BIGEARTHNET_DATASET_PATH", "")
    BIGEARTHNET_MODEL_PATH         = os.environ.get("BIGEARTHNET_MODEL_PATH", "")
    BIGEARTHNET_NUM_CLASSES        = int(os.environ.get("BIGEARTHNET_NUM_CLASSES", "19"))

    CHANGE_DETECTION_ENABLED       = _bool("CHANGE_DETECTION_ENABLED", True)  # uses fallback
    CHANGE_DETECTION_MODEL_PATH    = os.environ.get("CHANGE_DETECTION_MODEL_PATH", "")

    SAR_ANALYSIS_ENABLED           = _bool("SAR_ANALYSIS_ENABLED", False)
    SAR_MODEL_PATH                 = os.environ.get("SAR_MODEL_PATH", "")

    # Legacy — kept for backward compat
    LANDCOVER_MODEL_PATH           = os.environ.get("LANDCOVER_MODEL_PATH", "")

    # ── SMS / OTP ─────────────────────────────────────────────────────────────
    SMS_PROVIDER        = os.environ.get("SMS_PROVIDER", "")
    SMS_PROVIDER_API_KEY = os.environ.get("SMS_PROVIDER_API_KEY", "")
    SMS_PROVIDER_SECRET  = os.environ.get("SMS_PROVIDER_SECRET", "")
    SMS_SENDER_ID        = os.environ.get("SMS_SENDER_ID", "SATQRY")
    OTP_EXPIRY_MINUTES   = int(os.environ.get("OTP_EXPIRY_MINUTES", "10"))

    # ── Async jobs ────────────────────────────────────────────────────────────
    ANALYSIS_JOB_TIMEOUT = int(os.environ.get("ANALYSIS_JOB_TIMEOUT", "600"))
    RQ_QUEUES            = os.environ.get("RQ_QUEUES", "analysis,default")

    # ── Misc ──────────────────────────────────────────────────────────────────
    BCRYPT_LOG_ROUNDS = 12


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG             = False
    BCRYPT_LOG_ROUNDS = 14
    SEND_SECURITY_HEADERS = True


def get_config():
    env = os.environ.get("FLASK_ENV", "development").lower()
    return {"development": DevelopmentConfig, "production": ProductionConfig}.get(
        env, DevelopmentConfig
    )
