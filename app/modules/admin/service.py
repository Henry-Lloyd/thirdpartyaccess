"""Admin service — platform administration, broadcast notifications, provider management, settings."""

import os
from datetime import datetime, timezone
from app.database import get_db
from app.modules.notifications.service import create_notification
from app.modules.payments.service import get_provider_balance


# Admin email whitelist — configurable via ADMIN_EMAILS env var
# Supports comma-separated values, e.g. "admin1@example.com,admin2@example.com"
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "henrylloyd190@gmail.com").split(",")
    if e.strip()
]


def is_admin(email: str) -> bool:
    """Check if the given email is an admin."""
    return email.lower().strip() in ADMIN_EMAILS


def get_all_providers_with_balances() -> list:
    """Get all providers with their wallet balances and withdrawal amounts."""
    db = get_db()

    providers = db.execute(
        """SELECT p.id as provider_id, p.title, p.category, p.access_fee, p.verified,
                  p.created_at as profile_created,
                  u.id as user_id, u.email, u.first_name, u.last_name,
                  COALESCE(u.status, 'active') as status
           FROM providers p
           JOIN users u ON p.user_id = u.id
           ORDER BY u.first_name, u.last_name"""
    ).fetchall()

    results = []
    for prov in providers:
        prov = dict(prov)
        balance = get_provider_balance(prov["user_id"])

        # Count requests
        req_count = db.execute(
            "SELECT COUNT(*) as cnt FROM access_requests WHERE provider_id = ?",
            (prov["provider_id"],)
        ).fetchone()["cnt"]

        # Get user status
        user_status = prov.get("status", "active")

        results.append({
            "providerId": prov["provider_id"],
            "userId": prov["user_id"],
            "email": prov["email"],
            "firstName": prov["first_name"],
            "lastName": prov["last_name"],
            "fullName": f"{prov['first_name']} {prov['last_name']}",
            "title": prov["title"],
            "category": prov["category"],
            "accessFee": prov["access_fee"],
            "verified": bool(prov["verified"]),
            "profileCreated": prov["profile_created"],
            "totalEarnings": balance["totalEarnings"],
            "totalWithdrawn": balance["totalWithdrawn"],
            "pendingWithdrawals": balance["pendingWithdrawals"],
            "availableBalance": balance["availableBalance"],
            "totalRequests": req_count,
            "status": user_status,
        })

    return results


def get_all_seekers() -> list:
    """Get all seekers."""
    db = get_db()
    rows = db.execute(
        "SELECT id, email, first_name, last_name, created_at FROM users WHERE role = 'seeker' ORDER BY first_name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_users() -> list:
    """Get all users (both seekers and providers)."""
    db = get_db()
    rows = db.execute(
        "SELECT id, email, first_name, last_name, role, created_at, COALESCE(status, 'active') as status FROM users ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_platform_stats() -> dict:
    """Get platform-wide statistics for the admin dashboard."""
    db = get_db()

    total_users = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    total_seekers = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'seeker'").fetchone()["cnt"]
    total_providers = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'provider'").fetchone()["cnt"]
    total_requests = db.execute("SELECT COUNT(*) as cnt FROM access_requests").fetchone()["cnt"]
    total_completed = db.execute("SELECT COUNT(*) as cnt FROM access_requests WHERE status = 'completed'").fetchone()["cnt"]
    total_payments = db.execute("SELECT COUNT(*) as cnt FROM payments WHERE status = 'success'").fetchone()["cnt"]

    revenue_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total, COALESCE(SUM(platform_share), 0) as platform FROM payments WHERE status = 'success'"
    ).fetchone()

    return {
        "totalUsers": total_users,
        "totalSeekers": total_seekers,
        "totalProviders": total_providers,
        "totalRequests": total_requests,
        "totalCompleted": total_completed,
        "totalPayments": total_payments,
        "totalRevenue": revenue_row["total"],
        "platformRevenue": revenue_row["platform"],
    }


# ═══════════════════════════════════════════════════════════════
#  PLATFORM SETTINGS — Revenue Split Configuration
# ═══════════════════════════════════════════════════════════════

def get_revenue_split_setting() -> dict:
    """Retrieve the current provider revenue share percentage from the database."""
    db = get_db()
    row = db.execute(
        "SELECT value, updated_at, updated_by FROM platform_settings WHERE key = 'provider_revenue_share_percentage'"
    ).fetchone()
    if row:
        return {
            "providerPercentage": float(row["value"]),
            "platformPercentage": 100.0 - float(row["value"]),
            "updatedAt": row["updated_at"],
            "updatedBy": row["updated_by"],
        }
    # Fallback if the row doesn't exist yet
    return {
        "providerPercentage": 50.0,
        "platformPercentage": 50.0,
        "updatedAt": None,
        "updatedBy": None,
    }


def update_revenue_split(new_percentage: float, admin_email: str) -> dict:
    """Update the provider revenue share percentage and notify all providers.

    Args:
        new_percentage: The new provider share (0–100).
        admin_email: Email of the admin making the change.

    Returns:
        dict with success status and notification count.

    Raises:
        ValueError: If the percentage is out of range or not a number.
    """
    # Validate
    if not isinstance(new_percentage, (int, float)):
        raise ValueError("Percentage must be a numeric value.")
    if new_percentage < 0 or new_percentage > 100:
        raise ValueError("Percentage must be between 0 and 100.")

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Use a transaction: update setting + broadcast notifications
    db.execute(
        """INSERT INTO platform_settings (key, value, updated_at, updated_by)
           VALUES ('provider_revenue_share_percentage', ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                          updated_at = excluded.updated_at,
                                          updated_by = excluded.updated_by""",
        (str(new_percentage), now, admin_email),
    )

    # Broadcast notification to all providers
    providers = db.execute("SELECT id FROM users WHERE role = 'provider'").fetchall()
    notified = 0
    for prov in providers:
        try:
            create_notification(
                prov["id"],
                "revenue_split_update",
                "Revenue Share Updated",
                f"Important Update: Your revenue share percentage has been adjusted to {new_percentage:.1f}%. "
                f"This change applies to all new transactions going forward.",
            )
            notified += 1
        except Exception as e:
            print(f"Failed to notify provider {prov['id']}: {e}")

    db.commit()

    platform_pct = 100.0 - new_percentage
    print(f"Revenue split updated to {new_percentage}% (provider) / {platform_pct}% (platform) by {admin_email}. "
          f"Notified {notified} provider(s).")

    return {
        "success": True,
        "providerPercentage": new_percentage,
        "platformPercentage": platform_pct,
        "notifiedProviders": notified,
    }


# ═══════════════════════════════════════════════════════════════
#  BROADCAST NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

def broadcast_notification(title: str, message: str, target: str = "all") -> dict:
    """Send a notification to all users, only seekers, or only providers.

    target: 'all', 'seekers', 'providers'
    Returns count of notifications sent.
    """
    db = get_db()

    if target == "seekers":
        users = db.execute("SELECT id FROM users WHERE role = 'seeker'").fetchall()
    elif target == "providers":
        users = db.execute("SELECT id FROM users WHERE role = 'provider'").fetchall()
    else:
        users = db.execute("SELECT id FROM users").fetchall()

    count = 0
    for user in users:
        try:
            create_notification(user["id"], "admin_broadcast", title, message)
            count += 1
        except Exception as e:
            print(f"Failed to notify user {user['id']}: {e}")

    print(f"Broadcast notification sent to {count} users (target: {target})")
    return {"sent": count, "target": target}


# ── Provider/User Management ──────────────────────────────────

def suspend_provider(user_id: str) -> dict:
    """Suspend a provider account (set status to 'suspended')."""
    db = get_db()
    db.execute("UPDATE users SET status = 'suspended' WHERE id = ?", (user_id,))
    db.commit()

    # Notify the user
    try:
        create_notification(
            user_id, "admin_action",
            "Account Suspended",
            "Your account has been suspended by an administrator. Please contact support if you believe this is an error."
        )
    except Exception:
        pass

    print(f"User suspended: {user_id}")
    return {"success": True, "action": "suspended", "userId": user_id}


def unsuspend_provider(user_id: str) -> dict:
    """Re-activate a suspended provider account."""
    db = get_db()
    db.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
    db.commit()

    # Notify the user
    try:
        create_notification(
            user_id, "admin_action",
            "Account Reactivated",
            "Your account has been reactivated by an administrator. You can now use the platform again."
        )
    except Exception:
        pass

    print(f"User reactivated: {user_id}")
    return {"success": True, "action": "reactivated", "userId": user_id}


# ═══════════════════════════════════════════════════════════════
#  VERIFICATION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def get_pending_verification_requests() -> list:
    """Get all pending verification requests for admin review."""
    db = get_db()
    rows = db.execute("""
        SELECT vr.*, p.title as provider_title, p.category,
               u.first_name, u.last_name, u.email,
               p.id_document_path, p.selfie_path,
               p.verification_status as provider_verification_status,
               p.verified as provider_verified
        FROM verification_requests vr
        JOIN providers p ON vr.provider_id = p.id
        JOIN users u ON p.user_id = u.id
        ORDER BY vr.submitted_at ASC
    """).fetchall()
    return [dict(r) for r in rows]


def get_verification_requests_by_status(status: str = None) -> list:
    """Get verification requests, optionally filtered by status."""
    db = get_db()
    if status:
        rows = db.execute("""
            SELECT vr.*, p.title as provider_title, p.category,
                   u.first_name, u.last_name, u.email,
                   p.id_document_path, p.selfie_path
            FROM verification_requests vr
            JOIN providers p ON vr.provider_id = p.id
            JOIN users u ON p.user_id = u.id
            WHERE vr.status = ?
            ORDER BY vr.submitted_at ASC
        """, (status,)).fetchall()
    else:
        rows = db.execute("""
            SELECT vr.*, p.title as provider_title, p.category,
                   u.first_name, u.last_name, u.email,
                   p.id_document_path, p.selfie_path
            FROM verification_requests vr
            JOIN providers p ON vr.provider_id = p.id
            JOIN users u ON p.user_id = u.id
            ORDER BY vr.submitted_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def approve_provider_verification(provider_id: str, admin_id: str, notes: str = None) -> dict:
    """Approve a provider's verification request. Sets verified=1."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Get the latest pending request
    req = db.execute(
        "SELECT id FROM verification_requests WHERE provider_id = ? AND status = 'pending' ORDER BY submitted_at DESC LIMIT 1",
        (provider_id,)
    ).fetchone()

    if req:
        db.execute(
            "UPDATE verification_requests SET status = 'approved', admin_id = ?, notes = ?, processed_at = ? WHERE id = ?",
            (admin_id, notes, now, req['id'])
        )

    # Update provider
    db.execute(
        "UPDATE providers SET verified = 1, verification_status = 'approved', verification_notes = ?, updated_at = ? WHERE id = ?",
        (notes, now, provider_id)
    )
    db.commit()

    # Notify the provider
    provider = db.execute("SELECT user_id FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if provider:
        try:
            create_notification(
                provider['user_id'],
                'verification_approved',
                'Verification Approved!',
                'Congratulations! Your identity has been verified. A gold verification badge is now displayed on your profile.'
            )
        except Exception as e:
            print(f"Failed to notify provider {provider_id}: {e}")

    print(f"Provider {provider_id} verified by admin {admin_id}")
    return {"success": True, "action": "approved", "providerId": provider_id}


def reject_provider_verification(provider_id: str, admin_id: str, notes: str = "") -> dict:
    """Reject a provider's verification request. Sets verified=0 and records mandatory notes."""
    if not notes or not notes.strip():
        raise ValueError("Rejection notes are mandatory when rejecting a verification request.")

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Get the latest pending request
    req = db.execute(
        "SELECT id FROM verification_requests WHERE provider_id = ? AND status = 'pending' ORDER BY submitted_at DESC LIMIT 1",
        (provider_id,)
    ).fetchone()

    if req:
        db.execute(
            "UPDATE verification_requests SET status = 'rejected', admin_id = ?, notes = ?, processed_at = ? WHERE id = ?",
            (admin_id, notes.strip(), now, req['id'])
        )

    # Update provider
    db.execute(
        "UPDATE providers SET verified = 0, verification_status = 'rejected', verification_notes = ?, updated_at = ? WHERE id = ?",
        (notes.strip(), now, provider_id)
    )
    db.commit()

    # Notify the provider
    provider = db.execute("SELECT user_id FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if provider:
        try:
            create_notification(
                provider['user_id'],
                'verification_rejected',
                'Verification Not Approved',
                f'Your verification request was not approved. Reason: {notes.strip()}. You may re-upload your documents and try again.'
            )
        except Exception as e:
            print(f"Failed to notify provider {provider_id}: {e}")

    print(f"Provider {provider_id} verification rejected by admin {admin_id}")
    return {"success": True, "action": "rejected", "providerId": provider_id}


def send_verification_reminder(provider_id: str) -> dict:
    """Send a verification reminder notification to a provider."""
    db = get_db()
    provider = db.execute("SELECT user_id, verification_status, verified FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if not provider:
        raise ValueError("Provider not found")

    if provider['verified']:
        raise ValueError("Provider is already verified")

    try:
        create_notification(
            provider['user_id'],
            'verification_reminder',
            'Verification Reminder',
            'Please complete your identity verification to receive a gold badge on your profile. '
            'Upload your ID document and a selfie from your Provider Verification page.'
        )
    except Exception as e:
        print(f"Failed to send reminder to provider {provider_id}: {e}")
        raise ValueError(f"Failed to send reminder: {e}")

    print(f"Verification reminder sent to provider {provider_id}")
    return {"success": True, "providerId": provider_id}


def admin_delete_verification_documents(provider_id: str) -> dict:
    """Admin action: delete uploaded verification documents for a provider to save storage."""
    from app.modules.providers.service import delete_verification_documents
    return delete_verification_documents(provider_id)


def delete_provider_account(user_id: str) -> dict:
    """Delete a provider account and all associated data."""
    db = get_db()

    # Get provider info first
    provider = db.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
    provider_id = provider["id"] if provider else None

    if provider_id:
        # Delete related data in correct order (respecting foreign keys)
        db.execute("DELETE FROM reviews WHERE provider_id = ?", (provider_id,))
        db.execute("DELETE FROM payouts WHERE provider_id = ?", (provider_id,))
        db.execute("DELETE FROM payments WHERE provider_id = ?", (provider_id,))
        db.execute("DELETE FROM messages WHERE request_id IN (SELECT id FROM access_requests WHERE provider_id = ?)", (provider_id,))
        db.execute("DELETE FROM access_grants WHERE provider_id = ?", (provider_id,))
        db.execute("DELETE FROM access_requests WHERE provider_id = ?", (provider_id,))
        db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))

    # Delete notifications
    db.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM login_attempts WHERE email = (SELECT email FROM users WHERE id = ?)", (user_id,))

    # Delete the user record
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()

    print(f"User and all associated data deleted: {user_id}")
    return {"success": True, "action": "deleted", "userId": user_id}
