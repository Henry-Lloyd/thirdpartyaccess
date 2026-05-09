"""Application configuration — hostable anywhere."""

import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ── Environment ─────────────────────────────────────────────
    FLASK_ENV = os.environ.get("FLASK_ENV", "development").lower()

    # ── Core Security ───────────────────────────────────────────
    # Use explicit SECRET_KEY when provided. Fallback is safe for local/dev use.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")

    # ── Session Security ────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get("SESSION_TTL_HOURS", "1")))

    # ── Database ────────────────────────────────────────────────
    DATABASE_PATH = os.path.join(BASE_DIR, "data", "database.sqlite")
    BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")

    # ── Server ──────────────────────────────────────────────────
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max upload
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = int(os.environ.get("PORT", 3000))

    # ── PayChangu Payment Gateway ───────────────────────────────
    PAYCHANGU_SECRET_KEY = os.environ.get("PAYCHANGU_SECRET_KEY", "")
    PAYCHANGU_PUBLIC_KEY = os.environ.get("PAYCHANGU_PUBLIC_KEY", "")
    PAYCHANGU_API_URL = "https://api.paychangu.com"
    PAYCHANGU_WEBHOOK_SECRET = os.environ.get("PAYCHANGU_WEBHOOK_SECRET", "")

    # Base URL for callbacks (auto-detected or override)
    BASE_URL = os.environ.get("BASE_URL", "")
