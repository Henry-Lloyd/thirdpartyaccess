"""Database connection, schema initialization, and backup utilities."""

import os
import re
import sqlite3
import shutil
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import g, current_app


class PostgresCompatConnection:
    """SQLite-like adapter over psycopg2 connection.

    This preserves existing service-layer SQL usage (`?` placeholders and
    `db.execute(...).fetch*()` patterns) while using PostgreSQL in production.
    """

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=RealDictCursor)

    @staticmethod
    def _adapt_sql(sql: str) -> str:
        adapted = sql

        # sqlite placeholders -> psycopg placeholders
        adapted = adapted.replace("?", "%s")

        # sqlite upsert flavor used in this project
        adapted = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", adapted, flags=re.IGNORECASE)
        if "INSERT" in adapted.upper() and "OR IGNORE" not in adapted.upper() and "ON CONFLICT" not in adapted.upper():
            # No-op for most inserts; specific migrations handle ON CONFLICT explicitly.
            pass

        return adapted

    def execute(self, sql: str, params=None):
        cur = self._conn.cursor()
        cur.execute(self._adapt_sql(sql), params or ())
        return cur

    def executescript(self, script: str):
        cur = self._conn.cursor()
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        for stmt in statements:
            cur.execute(self._adapt_sql(stmt))
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def _create_sqlite_connection(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_db(close=False):
    """Get or close the database connection for the current request context."""
    if close:
        db = g.pop("db", None)
        if db is not None:
            db.close()
        return None

    if "db" not in g:
        backend = current_app.config.get("DB_BACKEND", "sqlite")
        if backend == "postgresql":
            database_url = current_app.config.get("DATABASE_URL")
            if not database_url:
                raise RuntimeError("DATABASE_URL is required when DB_BACKEND=postgresql")
            g.db = PostgresCompatConnection(database_url)
        else:
            db_path = current_app.config["DATABASE_PATH"]
            g.db = _create_sqlite_connection(db_path)

    return g.db


def get_db_direct(db_path=None):
    """Get a direct database connection (outside of Flask request context)."""
    backend = current_app.config.get("DB_BACKEND", "sqlite")
    if backend == "postgresql":
        database_url = current_app.config.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required when DB_BACKEND=postgresql")
        return PostgresCompatConnection(database_url)

    if not db_path:
        db_path = current_app.config["DATABASE_PATH"]
    return _create_sqlite_connection(db_path)


def init_db():
    """Initialize all database tables if they don't already exist (SQLite local mode only)."""
    if current_app.config.get("DB_BACKEND") == "postgresql":
        # Production PostgreSQL schema is managed by Flask-Migrate/Alembic.
        return

    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('seeker', 'provider')),
            phone_number TEXT,
            avatar TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(email, role)
        );

        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            bio TEXT,
            expertise TEXT,
            phone_number TEXT NOT NULL,
            hourly_rate REAL,
            access_fee REAL NOT NULL,
            request_approval_required INTEGER NOT NULL DEFAULT 1,
            profile_photo TEXT,
            category TEXT NOT NULL,
            offered_benefits TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS access_requests (
            id TEXT PRIMARY KEY,
            seeker_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'completed')),
            contact_email TEXT,
            contact_phone TEXT,
            released_data TEXT,
            access_fee_status TEXT NOT NULL CHECK(access_fee_status IN ('pending', 'paid', 'refunded')),
            payment_method TEXT,
            transaction_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS access_grants (
            id TEXT PRIMARY KEY,
            seeker_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL REFERENCES access_requests(id) ON DELETE CASCADE,
            contact_email TEXT NOT NULL,
            contact_phone TEXT,
            granted_data TEXT,
            granted_at TEXT NOT NULL,
            expires_at TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expired', 'revoked'))
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            from_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            to_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            request_id TEXT NOT NULL REFERENCES access_requests(id) ON DELETE CASCADE,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            related_request_id TEXT REFERENCES access_requests(id) ON DELETE CASCADE,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL REFERENCES access_requests(id) ON DELETE CASCADE,
            seeker_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            tx_ref TEXT UNIQUE NOT NULL,
            paychangu_checkout_url TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'MWK',
            platform_share REAL NOT NULL DEFAULT 0,
            provider_share REAL NOT NULL DEFAULT 0,
            split_percentage REAL NOT NULL DEFAULT 50.0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'success', 'failed', 'cancelled')),
            payment_channel TEXT,
            paychangu_reference TEXT,
            paychangu_charge_id TEXT,
            customer_email TEXT,
            customer_name TEXT,
            meta TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payouts (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            charge_id TEXT UNIQUE NOT NULL,
            payout_method TEXT NOT NULL CHECK(payout_method IN ('airtel_money', 'tnm_mpamba', 'bank_transfer')),
            recipient_name TEXT NOT NULL,
            recipient_account TEXT NOT NULL,
            bank_name TEXT,
            bank_uuid TEXT,
            mobile_operator_ref_id TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'MWK',
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'processing', 'successful', 'failed', 'cancelled')),
            paychangu_ref_id TEXT,
            paychangu_trans_id TEXT,
            paychangu_trace_id TEXT,
            failure_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- Reviews & Trust Score System
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL REFERENCES access_requests(id) ON DELETE CASCADE,
            reviewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            comment TEXT,
            is_verified_transaction INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(request_id, reviewer_id)
        );

        -- Login attempt tracking
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            ip_address TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            attempted_at TEXT NOT NULL
        );

        -- Platform Settings (global configuration, e.g. revenue split)
        CREATE TABLE IF NOT EXISTS platform_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT
        );

        -- Password Reset Tokens
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, attempted_at);
        CREATE INDEX IF NOT EXISTS idx_reviews_provider ON reviews(provider_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_request ON reviews(request_id);
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash ON password_reset_tokens(token_hash);
    """)

    # Migration: if users table has old-style UNIQUE(email) only, rebuild it
    _migrate_users_table(db)

    # Migration: add new JSON columns if they don't exist yet
    _migrate_add_json_columns(db)

    # Migration: add status column to users table
    _migrate_add_user_status(db)

    # Migration: add profile_pic column to users table
    _migrate_add_profile_pic(db)

    # Migration: seed default platform settings
    _migrate_seed_platform_settings(db)

    # Migration: add verification columns to providers table
    _migrate_add_verification_columns(db)

    # Migration: create verification_requests table
    _migrate_create_verification_requests(db)

    # Migration: create password_reset_tokens table
    _migrate_create_password_reset_tokens(db)

    db.commit()
    print("Database initialized successfully")


def _migrate_users_table(db):
    """Migrate users table from UNIQUE(email) to UNIQUE(email, role) if needed."""
    indexes = db.execute("PRAGMA index_list('users')").fetchall()

    needs_migration = False
    for idx in indexes:
        idx_info = db.execute(f"PRAGMA index_info('{idx['name']}')").fetchall()
        if idx["unique"] and len(idx_info) == 1:
            col_name = idx_info[0]["name"]
            if col_name == "email":
                needs_migration = True
                break

    if not needs_migration:
        return

    print("Migrating users table: UNIQUE(email) -> UNIQUE(email, role)...")

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users_new (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('seeker', 'provider')),
            phone_number TEXT,
            avatar TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(email, role)
        );

        INSERT OR IGNORE INTO users_new SELECT id, email, password_hash, first_name, last_name, role, phone_number, avatar, created_at FROM users;

        DROP TABLE users;

        ALTER TABLE users_new RENAME TO users;
    """)

    print("Users table migration complete.")


def _migrate_add_json_columns(db):
    """Add released_data, granted_data, offered_benefits columns to existing tables."""
    migrations = [
        ("access_requests", "released_data", "TEXT"),
        ("access_grants", "granted_data", "TEXT"),
        ("providers", "offered_benefits", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"Migration: added {column} to {table}")
        except Exception:
            pass  # Column already exists


def _migrate_add_user_status(db):
    """Add status column to users table for suspend/active functionality."""
    try:
        db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        print("Migration: added status column to users table")
    except Exception:
        pass  # Column already exists


def _migrate_add_profile_pic(db):
    """Add profile_pic column to users table for profile picture uploads."""
    try:
        db.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")
        print("Migration: added profile_pic column to users table")
    except Exception:
        pass  # Column already exists


def _migrate_seed_platform_settings(db):
    """Seed default platform settings if they don't exist yet."""
    from datetime import datetime, timezone as tz
    now = datetime.now(tz.utc).isoformat()
    try:
        db.execute(
            "INSERT OR IGNORE INTO platform_settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)",
            ("provider_revenue_share_percentage", "50.0", now, "system")
        )
    except Exception:
        pass  # Table may not exist yet on very first run — handled by CREATE TABLE IF NOT EXISTS above


def _migrate_add_verification_columns(db):
    """Add verification-related columns to the providers table."""
    columns = [
        ("providers", "id_document_path", "TEXT"),
        ("providers", "selfie_path", "TEXT"),
        ("providers", "verification_status", "TEXT NOT NULL DEFAULT 'pending'"),
        ("providers", "verification_notes", "TEXT"),
        ("providers", "verification_submitted_at", "TEXT"),
    ]
    for table, column, col_type in columns:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            print(f"Migration: added {column} to {table}")
        except Exception:
            pass  # Column already exists


def _migrate_create_verification_requests(db):
    """Create the verification_requests table if it doesn't exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS verification_requests (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
            id_document_path TEXT,
            selfie_path TEXT,
            submitted_at TEXT NOT NULL,
            admin_id TEXT REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
            notes TEXT,
            processed_at TEXT
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_verification_requests_provider ON verification_requests(provider_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_verification_requests_status ON verification_requests(status)")


def _migrate_create_password_reset_tokens(db):
    """Create the password_reset_tokens table if it doesn't exist."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash ON password_reset_tokens(token_hash)")


# ═══════════════════════════════════════════════════════════════
#  DATABASE BACKUP & PERSISTENCE UTILITIES
# ═════════════════════════=═════════════════════════════════════

def create_backup(app=None) -> str:
    """Create a timestamped backup of the SQLite database file."""
    if app is None:
        app = current_app._get_current_object()

    if app.config.get("DB_BACKEND") == "postgresql":
        raise RuntimeError("SQLite file backup is unavailable in PostgreSQL mode. Use pg_dump on Render Postgres.")

    db_path = app.config["DATABASE_PATH"]
    backup_dir = app.config.get("BACKUP_DIR", os.path.join(os.path.dirname(db_path), "backups"))
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"database_{timestamp}.sqlite"
    backup_path = os.path.join(backup_dir, backup_name)

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    source.backup(dest)
    dest.close()
    source.close()

    _cleanup_old_backups(backup_dir, keep=10)

    print(f"Database backup created: {backup_path}")
    return backup_path


def _cleanup_old_backups(backup_dir: str, keep: int = 10):
    """Remove oldest backups beyond the keep count."""
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith("database_") and f.endswith(".sqlite")],
        reverse=True,
    )
    for old_backup in backups[keep:]:
        os.remove(os.path.join(backup_dir, old_backup))
        print(f"Removed old backup: {old_backup}")


# ═══════════════════════════════════════════════════════════════
#  DATABASE EXPORT / IMPORT (JSON) — DATA PERSISTENCE
# ═══════════════════════════════════════════════════════════════

# All tables that should be exported/imported for data persistence
EXPORT_TABLES = [
    "users", "providers", "access_requests", "access_grants",
    "messages", "notifications", "payments", "payouts",
    "reviews", "login_attempts", "platform_settings",
    "verification_requests", "password_reset_tokens",
]


def export_all_data_json(app=None) -> dict:
    """Export ALL data from ALL tables as a JSON-serializable dict.

    This helper is SQLite-oriented for local/dev usage.
    """
    if app is None:
        app = current_app._get_current_object()

    if app.config.get("DB_BACKEND") == "postgresql":
        raise RuntimeError("JSON export helper is SQLite-oriented. Use PostgreSQL backup tooling in production.")

    db_path = app.config["DATABASE_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tables": {},
    }

    for table_name in EXPORT_TABLES:
        try:
            rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
            export["tables"][table_name] = [dict(row) for row in rows]
        except Exception as e:
            print(f"Warning: could not export table '{table_name}': {e}")
            export["tables"][table_name] = []

    conn.close()
    print(f"Exported {sum(len(v) for v in export['tables'].values())} total rows across {len(export['tables'])} tables")
    return export


def import_all_data_json(data: dict, app=None, merge: bool = True) -> dict:
    """Import ALL data from a JSON export dict into the database.

    SQLite-oriented helper for local/dev usage.
    """
    if app is None:
        app = current_app._get_current_object()

    if app.config.get("DB_BACKEND") == "postgresql":
        raise RuntimeError("JSON import helper is SQLite-oriented and disabled for PostgreSQL production.")

    db_path = app.config["DATABASE_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")  # Temporarily disable to allow any insert order

    tables = data.get("tables", {})
    summary = {}

    for table_name in EXPORT_TABLES:
        rows = tables.get(table_name, [])
        if not rows:
            summary[table_name] = 0
            continue

        if not merge:
            try:
                conn.execute(f"DELETE FROM {table_name}")
            except Exception:
                pass

        # Get column names from first row
        columns = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)
        insert_sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"

        count = 0
        for row in rows:
            try:
                values = [row.get(col) for col in columns]
                conn.execute(insert_sql, values)
                count += 1
            except Exception as e:
                print(f"Warning: failed to import row into '{table_name}': {e}")

        summary[table_name] = count

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()

    total = sum(summary.values())
    print(f"Imported {total} total rows across {len(summary)} tables")
    return summary
