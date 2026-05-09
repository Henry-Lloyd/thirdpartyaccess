"""Main application routes — dashboard, root redirect, and PWA support."""

from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, session, send_from_directory, current_app, jsonify

from app.modules.requests.service import get_user_access_requests
from app.modules.access.service import get_seeker_access_grants, get_provider_access_grants
from app.modules.payments.service import get_payment_history, get_provider_balance, get_current_provider_share_percentage
from app.modules.providers.service import get_provider_by_user_id

main_bp = Blueprint("main", __name__)


# ── PWA: Service Worker must be served from root scope ──
@main_bp.route("/sw.js")
def service_worker():
    return send_from_directory(
        current_app.static_folder, "sw.js",
        mimetype="application/javascript"
    )


@main_bp.route("/health")
def health_check():
    """Lightweight health check endpoint for uptime monitoring."""
    return jsonify({"status": "ok", "service": "thirdparty-access", "timestamp": datetime.now(timezone.utc).isoformat()})


@main_bp.route("/")
def index():
    # If user is already logged in, go straight to dashboard
    user = session.get("user")
    if user:
        return redirect(url_for("main.dashboard"))
    # Otherwise show the public homepage
    return render_template("home.html")


@main_bp.route("/dashboard")
def dashboard():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    # Load stats
    stats = {"requests": 0, "grants": 0, "payments": 0}
    balance = {"totalEarnings": 0, "totalWithdrawn": 0, "pendingWithdrawals": 0, "availableBalance": 0}

    try:
        requests_list = get_user_access_requests(user["id"], user["role"])
        stats["requests"] = len(requests_list)
    except Exception:
        pass

    try:
        if user["role"] == "seeker":
            grants = get_seeker_access_grants(user["id"])
        else:
            grants = get_provider_access_grants(user["id"])
        stats["grants"] = len(grants)
    except Exception:
        pass

    try:
        payments = get_payment_history(user["id"], user["role"])
        stats["payments"] = len([p for p in payments if p["status"] == "success"])
    except Exception:
        pass

    # Load provider balance and profile
    provider = None
    if user["role"] == "provider":
        try:
            balance = get_provider_balance(user["id"])
        except Exception:
            pass
        try:
            provider = get_provider_by_user_id(user["id"])
        except Exception:
            pass

    # Load current revenue split for dynamic display
    provider_pct = get_current_provider_share_percentage()
    split = {"providerPercentage": provider_pct, "platformPercentage": 100.0 - provider_pct}

    return render_template("dashboard/dashboard.html", user=user, stats=stats, balance=balance, split=split, provider=provider)

@main_bp.route("/about")
def about_page():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    return render_template("about.html", user=user)
