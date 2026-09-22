"""
SATQUERY AI — Flask Application Factory (Production-Ready)
"""

import logging
import logging.config
import os
import time

from flask import Flask, send_from_directory, jsonify, request, g
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from config import get_config
from database.models import db


# ─────────────────────────────────────────────────────────────────────────────
# Structured logging setup
# ─────────────────────────────────────────────────────────────────────────────

def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s request_id=%(request_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    # Add request_id to every log record
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.request_id = getattr(g, "request_id", "-") if _in_request_context() else "-"
        return record

    logging.setLogRecordFactory(record_factory)


def _in_request_context() -> bool:
    try:
        from flask import has_request_context
        return has_request_context()
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
        static_url_path="",
    )

    cfg = get_config()
    app.config.from_object(cfg)

    _configure_logging(app.config.get("DEBUG", False))
    logger = logging.getLogger("satquery.app")

    # ── Ensure directories ────────────────────────────────────────────────
    for folder_key in ("UPLOAD_FOLDER", "REPORTS_FOLDER"):
        path = app.config.get(folder_key)
        if path:
            os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "database"), exist_ok=True)

    # ── Extensions ────────────────────────────────────────────────────────
    db.init_app(app)
    jwt = JWTManager(app)

    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )

    # ── Rate limiting (optional — needs flask-limiter) ────────────────────
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            key_func=get_remote_address,
            app=app,
            storage_uri=app.config.get("RATELIMIT_STORAGE_URI", "memory://"),
            default_limits=[app.config.get("RATELIMIT_DEFAULT", "200 per minute")],
        )
        app.extensions["limiter"] = limiter
        logger.info("Rate limiter active.")
    except ImportError:
        logger.info("flask-limiter not installed — rate limiting disabled.")
        app.extensions["limiter"] = None

    # ── Request ID middleware ──────────────────────────────────────────────
    import uuid as _uuid

    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-Id", _uuid.uuid4().hex[:12])
        g.start_time = time.monotonic()

    @app.after_request
    def _add_headers(response):
        response.headers["X-Request-Id"] = getattr(g, "request_id", "-")
        elapsed_ms = round((time.monotonic() - getattr(g, "start_time", time.monotonic())) * 1000)
        response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

        # Security headers (safe for API + static file serving)
        if app.config.get("SEND_SECURITY_HEADERS", True):
            response.headers.setdefault("X-Content-Type-Options",  "nosniff")
            response.headers.setdefault("X-Frame-Options",          "SAMEORIGIN")
            response.headers.setdefault("Referrer-Policy",          "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy",
                "geolocation=(), microphone=(), camera=()",
            )
            # CSP — allow CDN resources the frontend uses
            response.headers.setdefault(
                "Content-Security-Policy",
                (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://unpkg.com https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
                    "img-src 'self' data: https://*.tile.openstreetmap.org https://server.arcgisonline.com; "
                    "font-src 'self' https://fonts.gstatic.com; "
                    "connect-src 'self' https://nominatim.openstreetmap.org;"
                ),
            )
        return response

    # ── JWT error handlers ────────────────────────────────────────────────
    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"success": False, "error": "Authentication required.", "detail": reason}), 401

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_data):
        return jsonify({"success": False, "error": "Session expired. Please log in again."}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"success": False, "error": "Invalid token.", "detail": reason}), 422

    # ── Register blueprints ───────────────────────────────────────────────
    from routes.auth           import auth_bp
    from routes.analysis       import analysis_bp
    from routes.coordinates    import coordinates_bp
    from routes.history        import history_bp
    from routes.reports        import reports_bp
    from routes.query          import query_bp
    from routes.progress       import progress_bp
    from routes.otp            import otp_bp
    from routes.training_agent import training_agent_bp

    app.register_blueprint(auth_bp,           url_prefix="/api/auth")
    app.register_blueprint(analysis_bp,       url_prefix="/api/analyze")
    app.register_blueprint(coordinates_bp,    url_prefix="/api/analyze")
    app.register_blueprint(history_bp,        url_prefix="/api/analysis")
    app.register_blueprint(reports_bp,        url_prefix="/api/report")
    app.register_blueprint(query_bp,          url_prefix="/api/query")
    app.register_blueprint(progress_bp,       url_prefix="/api/analysis")
    app.register_blueprint(otp_bp,            url_prefix="/api/auth")
    app.register_blueprint(training_agent_bp, url_prefix="/api/agent")

    # ── Serve uploaded files ──────────────────────────────────────────────
    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    # ── Frontend routes ───────────────────────────────────────────────────
    _PAGE_ROUTES = [
        ("/",          "login.html",    "page_root"),
        ("/login",     "login.html",    "page_login"),
        ("/register",  "register.html", "page_register"),
        ("/dashboard", "dashboard.html","page_dashboard"),
        ("/analysis",  "analysis.html", "page_analysis"),
        ("/results",   "results.html",  "page_results"),
        ("/history",   "history.html",  "page_history"),
        ("/profile",   "profile.html",  "page_profile"),
        ("/models",    "models.html",   "page_models"),
    ]
    for route, html, ep_name in _PAGE_ROUTES:
        _html = html
        app.add_url_rule(
            route,
            endpoint=ep_name,
            view_func=lambda h=_html: send_from_directory(app.static_folder, h),
        )

    # ── /health — liveness ────────────────────────────────────────────────
    @app.route("/health")
    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "app": app.config["APP_NAME"],
            "version": app.config["APP_VERSION"],
        }), 200

    # ── /ready — readiness (checks dependencies) ──────────────────────────
    @app.route("/ready")
    @app.route("/api/ready")
    def ready():
        checks = {}
        overall = True

        # PostgreSQL / SQLite
        try:
            db.session.execute(db.text("SELECT 1"))
            checks["database"] = {"status": "ok"}
        except Exception as exc:
            checks["database"] = {"status": "error", "detail": str(exc)}
            overall = False

        # Redis (optional)
        try:
            import redis as redis_lib
            r = redis_lib.from_url(
                app.config.get("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1,
            )
            r.ping()
            checks["redis"] = {"status": "ok"}
        except ImportError:
            checks["redis"] = {"status": "not_installed"}
        except Exception:
            checks["redis"] = {"status": "unavailable", "detail": "Redis not reachable"}
            # Redis is optional — don't fail readiness

        # Storage
        upload_path = app.config.get("UPLOAD_FOLDER", "")
        if upload_path and os.path.isdir(upload_path) and os.access(upload_path, os.W_OK):
            checks["storage"] = {"status": "ok", "path": upload_path}
        else:
            checks["storage"] = {"status": "error", "detail": f"Upload folder not writable: {upload_path}"}
            overall = False

        # ML registry (if initialised)
        try:
            from ml_service.registry import list_models_status
            checks["ml_models"] = list_models_status()
        except Exception:
            checks["ml_models"] = {"status": "not_initialised"}

        http_status = 200 if overall else 503
        return jsonify({"ready": overall, "checks": checks}), http_status

    # ── /api/models — model health ────────────────────────────────────────
    @app.route("/api/models")
    def models_status():
        try:
            from ml_service.registry import list_models_status
            statuses = list_models_status()
        except Exception as exc:
            statuses = {"error": str(exc)}
        return jsonify({"success": True, "models": statuses}), 200

    # ── Global error handlers ─────────────────────────────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"success": False, "error": "Bad request.", "detail": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Resource not found."}), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"success": False, "error": "Uploaded file exceeds the size limit."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"success": False, "error": "Too many requests. Please slow down."}), 429

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Unhandled 500: %s", e)
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

    # ── Database init ─────────────────────────────────────────────────────
    with app.app_context():
        db.create_all()

    # ── Startup validation ────────────────────────────────────────────────
    with app.app_context():
        flask_env = os.environ.get("FLASK_ENV", "development")
        from services.startup_validator import validate_startup
        validate_startup(flask_env)

    # ── Model registry initialisation ─────────────────────────────────────
    with app.app_context():
        try:
            import sys as _sys
            _root = os.path.join(os.path.dirname(__file__), "..")
            if _root not in _sys.path:
                _sys.path.insert(0, _root)
            from ml_service.registry import initialize_registry
            initialize_registry(app.config)
            logger.info("Model registry initialised.")
        except Exception as exc:
            logger.warning("Model registry init failed (non-fatal): %s", exc)

    logger.info("SATQUERY AI v%s started in %s mode.", app.config["APP_VERSION"], os.environ.get("FLASK_ENV", "development"))
    return app


if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port, debug=application.config.get("DEBUG", False))
