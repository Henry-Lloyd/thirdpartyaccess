"""ThirdParty Access - Flask Application Factory."""

import sys

from flask import Flask, session
from config import Config
from app.database import init_db, get_db
from app.extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_class)

    # Initialize SQLAlchemy + Flask-Migrate (migration management)
    db.init_app(app)
    migrate.init_app(app, db)

    if app.config.get("FLASK_ENV") == "production" and app.config.get("SECRET_KEY") == "dev-insecure-change-me":
        raise RuntimeError("SECRET_KEY must be set in production environment.")

    if not app.config.get("PAYCHANGU_SECRET_KEY") or not app.config.get("PAYCHANGU_PUBLIC_KEY"):
        print("WARNING: PayChangu keys not configured. Payments will not work.")

    # SQLite local bootstrap only. Production PostgreSQL schema must come from migrations.
    with app.app_context():
        if app.config.get("DB_BACKEND") == "sqlite":
            if "db" in sys.argv:
                app.logger.info("Skipping runtime SQLite bootstrap during Flask-Migrate command.")
            else:
                init_db()
        else:
            app.logger.info("PostgreSQL backend detected. Run migrations with 'flask --app run.py db upgrade'.")

    @app.before_request
    def enforce_permanent_session():
        # Keep users logged in only for PERMANENT_SESSION_LIFETIME
        session.permanent = True

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if app.config.get("FLASK_ENV") == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        return response

    # Register teardown
    @app.teardown_appcontext
    def close_connection(exception):
        get_db(close=True)

    # Register blueprints
    from app.modules.auth.routes import auth_bp
    from app.modules.providers.routes import providers_bp
    from app.modules.requests.routes import requests_bp
    from app.modules.access.routes import access_bp
    from app.modules.notifications.routes import notifications_bp
    from app.modules.payments.routes import payments_bp
    from app.modules.reviews.routes import reviews_bp
    from app.modules.admin.routes import admin_bp
    from app.routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(providers_bp)
    app.register_blueprint(requests_bp)
    app.register_blueprint(access_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(main_bp)

    return app
