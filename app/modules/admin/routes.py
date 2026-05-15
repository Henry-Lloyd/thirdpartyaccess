"""Admin routes — admin dashboard, provider list, broadcast notifications, settings."""

import json
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, Response, current_app

from app.modules.admin.service import (
    is_admin, get_all_providers_with_balances, get_platform_stats,
    broadcast_notification, get_all_users,
    suspend_provider, unsuspend_provider, delete_provider_account,
    get_revenue_split_setting, update_revenue_split,
    get_pending_verification_requests, get_verification_requests_by_status,
    approve_provider_verification, reject_provider_verification,
    send_verification_reminder, admin_delete_verification_documents,
)

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    """Check that the current session user is an admin provider."""
    user = session.get("user")
    if not user:
        return None, redirect(url_for("auth.login_page"))
    if not is_admin(user.get("email", "")):
        return None, redirect(url_for("main.dashboard"))
    return user, None


# ── Admin Dashboard ──────────────────────────────────────────

@admin_bp.route("/admin")
def admin_dashboard():
    user, err = _require_admin()
    if err:
        return err

    stats = get_platform_stats()
    providers = get_all_providers_with_balances()
    users = get_all_users()
    split = get_revenue_split_setting()

    verification_requests = get_pending_verification_requests()

    return render_template("admin/dashboard.html",
                           user=user, stats=stats, providers=providers, users=users, split=split,
                           verification_requests=verification_requests)


# ── Admin Settings Page ───────────────────────────────────────

@admin_bp.route("/admin/settings")
def admin_settings():
    user, err = _require_admin()
    if err:
        return err

    split = get_revenue_split_setting()
    return render_template("admin/settings.html", user=user, split=split)


@admin_bp.route("/admin/settings/revenue_split", methods=["POST"])
def admin_update_revenue_split():
    """Handle form-based revenue split update from the admin settings page."""
    user, err = _require_admin()
    if err:
        return err

    pct_str = request.form.get("provider_percentage", "").strip()
    try:
        pct = float(pct_str)
    except (ValueError, TypeError):
        return redirect(url_for("admin.admin_settings", error="Invalid number. Please enter a value between 0 and 100."))

    try:
        result = update_revenue_split(pct, user.get("email", ""))
        return redirect(url_for("admin.admin_settings",
                                success="1",
                                new_pct=f"{pct:.1f}",
                                notified=result["notifiedProviders"]))
    except ValueError as e:
        return redirect(url_for("admin.admin_settings", error=str(e)))


# ── Broadcast Notification ───────────────────────────────────

@admin_bp.route("/admin/broadcast", methods=["POST"])
def admin_broadcast():
    user, err = _require_admin()
    if err:
        return err

    title = request.form.get("title", "").strip()
    message = request.form.get("message", "").strip()
    target = request.form.get("target", "all")

    if not title or not message:
        return redirect(url_for("admin.admin_dashboard"))

    result = broadcast_notification(title, message, target)
    return redirect(url_for("admin.admin_dashboard", broadcast_sent=result["sent"]))


# ── API Endpoints ────────────────────────────────────────────

@admin_bp.route("/api/admin/providers")
def api_admin_providers():
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    providers = get_all_providers_with_balances()
    return jsonify(providers)


@admin_bp.route("/api/admin/stats")
def api_admin_stats():
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    stats = get_platform_stats()
    return jsonify(stats)


# ── Revenue Split API ────────────────────────────────────────

@admin_bp.route("/api/admin/settings/revenue_split", methods=["GET"])
def api_get_revenue_split():
    """API: Get current revenue split setting."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    split = get_revenue_split_setting()
    return jsonify(split)


@admin_bp.route("/api/admin/settings/revenue_split", methods=["POST"])
def api_update_revenue_split():
    """API: Update the provider revenue share percentage.

    Expects JSON body: {"provider_percentage": <number 0-100>}
    Validates input, updates DB, and broadcasts notification to all providers.
    """
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    pct_raw = data.get("provider_percentage")
    if pct_raw is None:
        return jsonify({"error": "provider_percentage is required"}), 400

    try:
        pct = float(pct_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "provider_percentage must be a valid number"}), 400

    try:
        result = update_revenue_split(pct, user.get("email", ""))
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@admin_bp.route("/api/admin/broadcast", methods=["POST"])
def api_admin_broadcast():
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    title = data.get("title", "").strip()
    message = data.get("message", "").strip()
    target = data.get("target", "all")

    if not title or not message:
        return jsonify({"error": "Title and message are required"}), 400

    result = broadcast_notification(title, message, target)
    return jsonify(result)


# ── Verification Management Routes ──────────────────────────

@admin_bp.route("/admin/verify/<provider_id>", methods=["POST"])
def admin_verify_provider(provider_id):
    """Approve a provider's verification."""
    user, err = _require_admin()
    if err:
        return err
    notes = request.form.get("notes", "").strip()
    approve_provider_verification(provider_id, user.get("id", ""), notes)
    return redirect(url_for("admin.admin_dashboard", action="verified"))


@admin_bp.route("/admin/reject/<provider_id>", methods=["POST"])
def admin_reject_provider(provider_id):
    """Reject a provider's verification."""
    user, err = _require_admin()
    if err:
        return err
    notes = request.form.get("notes", "").strip()
    try:
        reject_provider_verification(provider_id, user.get("id", ""), notes)
    except ValueError as e:
        return redirect(url_for("admin.admin_dashboard", action="error", msg=str(e)))
    return redirect(url_for("admin.admin_dashboard", action="rejected"))


@admin_bp.route("/admin/send_reminder/<provider_id>", methods=["POST"])
def admin_send_reminder(provider_id):
    """Send a verification reminder to a provider."""
    user, err = _require_admin()
    if err:
        return err
    try:
        send_verification_reminder(provider_id)
    except ValueError as e:
        return redirect(url_for("admin.admin_dashboard", action="error", msg=str(e)))
    return redirect(url_for("admin.admin_dashboard", action="reminder_sent"))


@admin_bp.route("/admin/delete_docs/<provider_id>", methods=["POST"])
def admin_delete_docs(provider_id):
    """Delete verification documents for a provider."""
    user, err = _require_admin()
    if err:
        return err
    admin_delete_verification_documents(provider_id)
    return redirect(url_for("admin.admin_dashboard", action="docs_deleted"))


# ── Verification API Endpoints ───────────────────────────────

@admin_bp.route("/api/admin/verification_requests", methods=["GET"])
def api_verification_requests():
    """API: Get verification requests, optionally filtered by status."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    status_filter = request.args.get("status")
    requests_list = get_verification_requests_by_status(status_filter)
    return jsonify(requests_list)


@admin_bp.route("/api/admin/verify_provider/<provider_id>", methods=["POST"])
def api_verify_provider(provider_id):
    """API: Approve a provider's verification."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    notes = data.get("notes", "")
    result = approve_provider_verification(provider_id, user.get("id", ""), notes)
    return jsonify(result)


@admin_bp.route("/api/admin/reject_provider/<provider_id>", methods=["POST"])
def api_reject_provider(provider_id):
    """API: Reject a provider's verification."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json() or {}
    notes = data.get("notes", "")
    try:
        result = reject_provider_verification(provider_id, user.get("id", ""), notes)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@admin_bp.route("/api/admin/send_verification_reminder/<provider_id>", methods=["POST"])
def api_send_reminder(provider_id):
    """API: Send a verification reminder to a provider."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    try:
        result = send_verification_reminder(provider_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@admin_bp.route("/api/admin/delete_verification_documents/<provider_id>", methods=["DELETE"])
def api_delete_docs(provider_id):
    """API: Delete verification documents for a provider."""
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    result = admin_delete_verification_documents(provider_id)
    return jsonify(result)


# ── Provider Management Actions ─────────────────────────────

@admin_bp.route("/admin/suspend/<user_id>", methods=["POST"])
def admin_suspend_provider(user_id):
    user, err = _require_admin()
    if err:
        return err
    result = suspend_provider(user_id)
    return redirect(url_for("admin.admin_dashboard", action="suspended"))


@admin_bp.route("/admin/unsuspend/<user_id>", methods=["POST"])
def admin_unsuspend_provider(user_id):
    user, err = _require_admin()
    if err:
        return err
    result = unsuspend_provider(user_id)
    return redirect(url_for("admin.admin_dashboard", action="reactivated"))


@admin_bp.route("/admin/delete/<user_id>", methods=["POST"])
def admin_delete_provider(user_id):
    user, err = _require_admin()
    if err:
        return err
    # Prevent admin from deleting themselves
    if user_id == user.get("id"):
        return redirect(url_for("admin.admin_dashboard", action="error", msg="Cannot delete your own account"))
    result = delete_provider_account(user_id)
    return redirect(url_for("admin.admin_dashboard", action="deleted"))


# API versions of the management endpoints
@admin_bp.route("/api/admin/suspend/<user_id>", methods=["POST"])
def api_admin_suspend(user_id):
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    result = suspend_provider(user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/unsuspend/<user_id>", methods=["POST"])
def api_admin_unsuspend(user_id):
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    result = unsuspend_provider(user_id)
    return jsonify(result)


@admin_bp.route("/api/admin/delete/<user_id>", methods=["POST"])
def api_admin_delete(user_id):
    user = session.get("user")
    if not user or not is_admin(user.get("email", "")):
        return jsonify({"error": "Unauthorized"}), 403
    if user_id == user.get("id"):
        return jsonify({"error": "Cannot delete your own account"}), 400
    result = delete_provider_account(user_id)
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
#  DATABASE EXPORT / IMPORT (Data Persistence)
# ═══════════════════════════════════════════════════════════════

@admin_bp.route("/admin/export-data")
def admin_export_data():
    """Download all database data as a JSON file for data persistence."""
    user, err = _require_admin()
    if err:
        return err

    from app.database import export_all_data_json
    data = export_all_data_json()

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"thirdparty_access_data_{timestamp}.json"

    json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)

    return Response(
        json_str,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@admin_bp.route("/admin/import-data", methods=["POST"])
def admin_import_data():
    """Import database data from a JSON file (merge mode — existing data is updated)."""
    user, err = _require_admin()
    if err:
        return err

    if "data_file" not in request.files:
        return redirect(url_for("admin.admin_settings", import_error="No file selected"))

    file = request.files["data_file"]
    if file.filename == "":
        return redirect(url_for("admin.admin_settings", import_error="No file selected"))

    if not file.filename.lower().endswith(".json"):
        return redirect(url_for("admin.admin_settings", import_error="Only JSON files are accepted"))

    try:
        file_data = file.read()
        if len(file_data) > 100 * 1024 * 1024:  # 100MB limit
            return redirect(url_for("admin.admin_settings", import_error="File too large (max 100MB)"))

        data = json.loads(file_data)

        if "tables" not in data:
            return redirect(url_for("admin.admin_settings", import_error="Invalid data file format — missing 'tables' key"))

        # Create a backup before importing
        from app.database import create_backup
        try:
            create_backup()
        except Exception as e:
            print(f"Warning: backup before import failed: {e}")

        from app.database import import_all_data_json
        summary = import_all_data_json(data, merge=True)

        total_rows = sum(summary.values())
        return redirect(url_for("admin.admin_settings",
                                import_success="1",
                                import_rows=str(total_rows),
                                import_tables=str(len([k for k, v in summary.items() if v > 0]))))

    except json.JSONDecodeError:
        return redirect(url_for("admin.admin_settings", import_error="Invalid JSON file"))
    except Exception as e:
        return redirect(url_for("admin.admin_settings", import_error=f"Import failed: {str(e)}"))


@admin_bp.route("/admin/backup-sqlite")
def admin_backup_sqlite():
    """Download a raw SQLite backup of the database."""
    user, err = _require_admin()
    if err:
        return err

    from app.database import create_backup

    if current_app.config.get("DB_BACKEND") == "postgresql":
        return jsonify({
            "error": "SQLite backup endpoint is disabled in PostgreSQL mode.",
            "hint": "Use Render Postgres backups/pg_dump for production backups."
        }), 400

    backup_path = create_backup()

    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"thirdparty_access_db_{timestamp}.sqlite"

    with open(backup_path, "rb") as f:
        data = f.read()

    return Response(
        data,
        mimetype="application/x-sqlite3",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
