import os
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, request, session, g, jsonify
from config import Config
from database.connection import get_db, init_db_indexes, check_db_connection
from services.auth_service import get_current_user, generate_csrf_token, validate_csrf
from routes import auth_bp, item_bp, claim_bp, dashboard_bp, admin_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("findmate")

def create_app():
    """Application factory for FindMate Campus Lost & Found."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure uploads directories exist
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config.get("PRIVATE_UPLOAD_FOLDER", os.path.join(app.root_path, "private_uploads", "verification_photos")), exist_ok=True)

    # Initialize Cloudinary configuration
    try:
        from services.cloudinary_service import configure_cloudinary
        configure_cloudinary()
    except Exception as c_init_err:
        logger.warning("Could not initialize Cloudinary at startup: %s", c_init_err)

    # Configure Smart URL Handling for Cloudinary Images across all templates
    original_app_url_for = app.url_for
    original_jinja_url_for = app.jinja_env.globals.get("url_for")

    def smart_url_for(endpoint, **values):
        if endpoint == "static":
            filename = values.get("filename", "")
            if isinstance(filename, str):
                if filename.startswith("uploads/http://") or filename.startswith("uploads/https://"):
                    return filename[len("uploads/"):]
                if filename.startswith("http://") or filename.startswith("https://"):
                    return filename
        if callable(original_app_url_for):
            return original_app_url_for(endpoint, **values)
        elif callable(original_jinja_url_for):
            return original_jinja_url_for(endpoint, **values)
        return ""

    app.url_for = smart_url_for
    app.jinja_env.globals["url_for"] = smart_url_for

    # Verify MongoDB connection and initialize indexes
    with app.app_context():
        try:
            connected, msg = check_db_connection()
            if connected:
                logger.info("MongoDB status: %s", msg)
                init_db_indexes()
            else:
                logger.error("MongoDB check failed: %s", msg)
        except Exception as exc:
            logger.error("Error connecting to MongoDB during app startup: %s", exc)

    # Register Route Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(item_bp)
    app.register_blueprint(claim_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)

    # CSRF Protection Hook
    @app.before_request
    def csrf_protect():
        # Skip static files, health checks, and test mode if disabled
        if request.endpoint == "static" or request.path.startswith("/static"):
            return
        if request.path == "/health":
            return
        if app.config.get("TESTING") and not app.config.get("WTF_CSRF_ENABLED", True):
            return
        validate_csrf()

    def mask_phone_str(phone):
        if not phone:
            return "XXXXXXXXXX"
        digits = "".join(c for c in str(phone) if c.isdigit())
        if len(digits) >= 10:
            return f"{digits[:3]}XXXXXX{digits[-2:]}"
        elif len(digits) >= 6:
            return f"{digits[:2]}{'X' * (len(digits) - 4)}{digits[-2:]}"
        return "XXXXXX" + digits[-2:] if len(digits) >= 2 else "XXXXXXXXXX"

    # Context Processors for Templates
    @app.context_processor
    def inject_context():
        local_today = datetime.now().date()
        return {
            "current_user": get_current_user(),
            "csrf_token": generate_csrf_token,
            "now": datetime.now(timezone.utc),
            "today_date": local_today.strftime("%Y-%m-%d"),
            "today_formatted": local_today.strftime("%d %b %Y"),
            "mask_phone": mask_phone_str,
            "app_name": Config.APP_NAME,
            "app_tagline": Config.APP_TAGLINE,
            "campus_name": Config.CAMPUS_NAME
        }

    @app.template_filter("mask_phone")
    def mask_phone_filter(val):
        return mask_phone_str(val)

    # Custom Jinja Filters
    @app.template_filter("time_ago")
    def time_ago_filter(dt):
        """Format datetime into human friendly relative time like '18m ago' or '18 Oct 2026'."""
        if not dt:
            return ""
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                return dt

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - dt

        seconds = int(diff.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 7:
            return f"{days}d ago"
        return dt.strftime("%d %b %Y")

    @app.template_filter("format_date")
    def format_date_filter(val):
        """Format date string or datetime into consistent format like '18 Oct 2026'."""
        if not val:
            return ""
        if isinstance(val, datetime):
            return val.strftime("%d %b %Y")
        if isinstance(val, str):
            try:
                parsed = datetime.strptime(val[:10], "%Y-%m-%d")
                return parsed.strftime("%d %b %Y")
            except Exception:
                return val
        return str(val)

    # Health check endpoint
    @app.route("/health")
    def health():
        connected, msg = check_db_connection()
        status_code = 200 if connected else 503
        return jsonify({
            "status": "healthy" if connected else "unhealthy",
            "database": msg,
            "service": "FindMate Campus Lost & Found"
        }), status_code

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(403)
    def forbidden_error(e):
        return render_template("404.html", error_title="Access Forbidden (403)", error_msg="You do not have permission to view or modify this campus resource."), 403

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return render_template("404.html", error_title="File Too Large (413)", error_msg="Uploaded image exceeds the maximum permitted limit of 5MB. Please choose a smaller photo."), 413

    @app.errorhandler(500)
    def internal_server_error(e):
        logger.error("Server 500 error: %s", e)
        return render_template("500.html"), 500

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "127.0.0.1")
    use_reloader = os.getenv("FLASK_USE_RELOADER", "false").lower() in ("true", "1", "t")
    logger.info("Starting FindMate development server at http://%s:%s", host, port)
    app.run(host=host, port=port, debug=True, use_reloader=use_reloader)
