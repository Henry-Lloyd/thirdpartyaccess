"""Authentication service — register, login, get user.

Supports dual-role accounts: the same email can register as both a seeker
AND a provider (separate user rows with the same email but different roles).

Includes password validation (min 8 chars, at least one letter and one number)
and login attempt tracking.
"""

import hashlib
import uuid
import re
import bcrypt
from datetime import datetime, timezone, timedelta
from app.database import get_db


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored hash.

    Supports bcrypt hashes and legacy SHA-256 hashes for backward compatibility.
    """
    if not stored_hash:
        return False

    if stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
        except ValueError:
            return False

    # Legacy SHA-256 support for existing users
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


# ── Input Validation ───────────────────────────────────────────

def _validate_email(email: str) -> str:
    """Validate and normalize email address."""
    email = email.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise ValueError("Please enter a valid email address")
    if len(email) > 254:
        raise ValueError("Email address is too long")
    return email


def _validate_name(name: str, field: str) -> str:
    """Validate name fields: strip, check length, reject HTML/scripts."""
    name = name.strip()
    if not name or len(name) < 1:
        raise ValueError(f"{field} is required")
    if len(name) > 100:
        raise ValueError(f"{field} must be 100 characters or fewer")
    if re.search(r'[<>{}]', name):
        raise ValueError(f"{field} contains invalid characters")
    return name


def _validate_password(password: str) -> str:
    """Enforce password strength rules: min 8 chars, at least one letter and one number."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(password) > 128:
        raise ValueError("Password must be 128 characters or fewer")
    if not re.search(r'[A-Za-z]', password):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r'[0-9]', password):
        raise ValueError("Password must contain at least one number")
    return password


# ── Login Attempt Tracking ─────────────────────────────────────

def _record_login_attempt(email: str, ip_address: str, success: bool):
    """Record a login attempt for rate-limiting and audit."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO login_attempts (email, ip_address, success, attempted_at) VALUES (?, ?, ?, ?)",
        (email, ip_address, 1 if success else 0, now),
    )
    db.commit()


def _check_login_lockout(email: str) -> bool:
    """Check if an account is temporarily locked due to too many failed attempts.

    Uses Python datetime parsing against ISO timestamps stored in the DB.
    Returns True if 5+ failed attempts happened in the last 15 minutes.
    """
    db = get_db()
    rows = db.execute(
        """SELECT attempted_at FROM login_attempts
           WHERE email = ? AND success = 0
           ORDER BY attempted_at DESC
           LIMIT 20""",
        (email,),
    ).fetchall()

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent_failed_attempts = 0

    for row in rows:
        attempted_raw = row["attempted_at"]
        try:
            attempted_at = datetime.fromisoformat(attempted_raw)
            if attempted_at.tzinfo is None:
                attempted_at = attempted_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue

        if attempted_at > cutoff:
            recent_failed_attempts += 1

    return recent_failed_attempts >= 5


# ── Core Auth Functions ────────────────────────────────────────

def register_user(email: str, password: str, first_name: str, last_name: str, role: str) -> dict:
    """Register a new user account.

    The same email may register once as 'seeker' and once as 'provider'.
    A duplicate (email + role) pair raises ValueError.
    """
    # Validate all inputs
    email = _validate_email(email)
    first_name = _validate_name(first_name, "First name")
    last_name = _validate_name(last_name, "Last name")
    _validate_password(password)

    if role not in ("seeker", "provider"):
        raise ValueError("Invalid role")

    db = get_db()

    # Check if this email+role combo already exists
    existing = db.execute(
        "SELECT id FROM users WHERE email = ? AND role = ?", (email, role)
    ).fetchone()
    if existing:
        raise ValueError(f"A {role} account with this email already exists. Please login instead.")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    created_at = datetime.now(timezone.utc).isoformat()

    db.execute(
        "INSERT INTO users (id, email, password_hash, first_name, last_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, email, password_hash, first_name, last_name, role, created_at),
    )
    db.commit()

    print(f"User registered: {email} ({role})")
    return {"id": user_id, "email": email, "firstName": first_name, "lastName": last_name, "role": role}


def login_user(email: str, password: str, role: str, ip_address: str = "unknown") -> dict:
    """Authenticate a user by email, password, and role.

    The role parameter is required because the same email can have two accounts.
    """
    if role not in ("seeker", "provider"):
        raise ValueError("Invalid role")

    email = _validate_email(email)

    # Check for account lockout
    if _check_login_lockout(email):
        raise ValueError("Too many failed login attempts. Please try again in 15 minutes.")

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE email = ? AND role = ?", (email, role)
    ).fetchone()
    if not user:
        _record_login_attempt(email, ip_address, False)
        raise ValueError(f"No {role} account found with this email")

    if not verify_password(password, user["password_hash"]):
        _record_login_attempt(email, ip_address, False)
        raise ValueError("Invalid email or password")

    # Upgrade legacy SHA-256 hash to bcrypt on successful login
    if not user["password_hash"].startswith("$2"):
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user["id"]),
        )
        db.commit()

    # Check if account is suspended
    user_status = user["status"] if "status" in user.keys() else "active"
    if user_status == "suspended":
        raise ValueError("Your account has been suspended. Please contact support.")

    # Record successful login
    _record_login_attempt(email, ip_address, True)

    # Check if this user also has the other role
    other_role = "provider" if role == "seeker" else "seeker"
    other_account = db.execute(
        "SELECT id FROM users WHERE email = ? AND role = ?", (email, other_role)
    ).fetchone()

    # Get profile_pic
    profile_pic = None
    try:
        profile_pic = user["profile_pic"]
    except (IndexError, KeyError):
        pass

    print(f"User logged in: {email} as {role}")
    return {
        "id": user["id"],
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "role": user["role"],
        "hasOtherRole": other_account is not None,
        "profilePic": profile_pic,
    }


def switch_role(email: str, target_role: str) -> dict:
    """Switch to the other role for the same email (no password re-entry needed)."""
    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE email = ? AND role = ?", (email, target_role)
    ).fetchone()
    if not user:
        raise ValueError(f"No {target_role} account found for this email")

    other_role = "provider" if target_role == "seeker" else "seeker"
    other_account = db.execute(
        "SELECT id FROM users WHERE email = ? AND role = ?", (email, other_role)
    ).fetchone()

    # Get profile_pic
    profile_pic = None
    try:
        profile_pic = user["profile_pic"]
    except (IndexError, KeyError):
        pass

    print(f"User switched role: {email} -> {target_role}")
    return {
        "id": user["id"],
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "role": user["role"],
        "hasOtherRole": other_account is not None,
        "profilePic": profile_pic,
    }


# ── Password Reset Functions ───────────────────────────────────

def request_password_reset(email: str, role: str) -> dict:
    """Generate a password reset token for the given email+role.

    Returns a dict with the token (to be shown/emailed to the user)
    and the token_id.  The token is valid for 30 minutes.

    Since this is a self-hosted app without email service, the reset
    link/token is displayed directly to the user on a confirmation page.
    """
    if role not in ("seeker", "provider"):
        raise ValueError("Invalid role")

    email = _validate_email(email)
    db = get_db()

    user = db.execute(
        "SELECT id, email, first_name, last_name, role FROM users WHERE email = ? AND role = ?",
        (email, role),
    ).fetchone()
    if not user:
        # Don't reveal whether account exists — still return success-like response
        raise ValueError("If an account with this email and role exists, a reset link has been generated.")

    # Invalidate any existing unused tokens for this user
    db.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0",
        (user["id"],),
    )

    # Generate a secure random token
    import secrets
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    token_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + __import__("datetime").timedelta(minutes=30)

    db.execute(
        """INSERT INTO password_reset_tokens (id, user_id, token_hash, role, created_at, expires_at, used)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (token_id, user["id"], token_hash, role, now.isoformat(), expires_at.isoformat()),
    )
    db.commit()

    print(f"Password reset token generated for {email} ({role})")
    return {
        "token": raw_token,
        "tokenId": token_id,
        "email": email,
        "role": role,
        "expiresAt": expires_at.isoformat(),
    }


def verify_reset_token(token: str) -> dict | None:
    """Verify a password reset token is valid and not expired.

    Returns user info dict if valid, None if invalid/expired.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()

    row = db.execute(
        """SELECT prt.*, u.email, u.first_name, u.last_name
           FROM password_reset_tokens prt
           JOIN users u ON prt.user_id = u.id
           WHERE prt.token_hash = ? AND prt.used = 0""",
        (token_hash,),
    ).fetchone()

    if not row:
        return None

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    now = datetime.now(timezone.utc)
    if now > expires_at:
        # Mark as used (expired)
        db.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = ?", (row["id"],))
        db.commit()
        return None

    return {
        "tokenId": row["id"],
        "userId": row["user_id"],
        "email": row["email"],
        "firstName": row["first_name"],
        "lastName": row["last_name"],
        "role": row["role"],
    }


def reset_password(token: str, new_password: str) -> dict:
    """Reset a user's password using a valid reset token.

    Validates the token, enforces password rules, updates the password,
    and marks the token as used.
    """
    # Verify token
    token_info = verify_reset_token(token)
    if not token_info:
        raise ValueError("Invalid or expired reset link. Please request a new one.")

    # Validate new password
    _validate_password(new_password)

    # Update password
    db = get_db()
    new_hash = hash_password(new_password)
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (new_hash, token_info["userId"]),
    )

    # Mark token as used
    db.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE id = ?",
        (token_info["tokenId"],),
    )
    db.commit()

    print(f"Password reset successful for {token_info['email']} ({token_info['role']})")
    return {
        "success": True,
        "email": token_info["email"],
        "role": token_info["role"],
    }


def get_user_by_id(user_id: str) -> dict | None:
    """Get user details by ID."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return None

    other_role = "provider" if user["role"] == "seeker" else "seeker"
    other_account = db.execute(
        "SELECT id FROM users WHERE email = ? AND role = ?", (user["email"], other_role)
    ).fetchone()

    # Get profile_pic
    profile_pic = None
    try:
        profile_pic = user["profile_pic"]
    except (IndexError, KeyError):
        pass

    return {
        "id": user["id"],
        "email": user["email"],
        "firstName": user["first_name"],
        "lastName": user["last_name"],
        "role": user["role"],
        "hasOtherRole": other_account is not None,
        "profilePic": profile_pic,
    }
