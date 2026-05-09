"""Access grant routes — API + page routes for viewing access grants."""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session

from app.modules.access.service import get_seeker_access_grants, get_provider_access_grants

access_bp = Blueprint("access", __name__)


# ── API Endpoints ──────────────────────────────────────────────

@access_bp.route("/api/access-grants/seeker/<seeker_id>", methods=["GET"])
def api_seeker_grants(seeker_id):
    try:
        grants = get_seeker_access_grants(seeker_id)
        return jsonify(grants)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@access_bp.route("/api/access-grants/provider/<user_id>", methods=["GET"])
def api_provider_grants(user_id):
    try:
        grants = get_provider_access_grants(user_id)
        return jsonify(grants)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Page Routes ──────────────────────────────────────────────

@access_bp.route("/my-access")
def my_access_page():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if user["role"] == "seeker":
        grants = get_seeker_access_grants(user["id"])
    else:
        grants = get_provider_access_grants(user["id"])

    return render_template("access/my_access.html", user=user, grants=grants)
