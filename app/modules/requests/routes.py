"""Request routes — API + page routes for access request workflow."""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session

from app.modules.requests.service import (
    create_access_request, get_access_request, get_user_access_requests,
    update_access_request_status, update_access_fee_payment_status,
    release_provider_contact,
)
from app.modules.payments.service import get_current_provider_share_percentage

requests_bp = Blueprint("requests", __name__)


# ── API Endpoints ──────────────────────────────────────────────

@requests_bp.route("/api/requests", methods=["POST"])
def api_create_request():
    try:
        data = request.get_json()
        result = create_access_request(data["seekerId"], data["providerId"], data["purpose"])
        return jsonify(result)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@requests_bp.route("/api/requests/<request_id>", methods=["GET"])
def api_get_request(request_id):
    try:
        result = get_access_request(request_id)
        if not result:
            return jsonify({"error": "Request not found"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requests_bp.route("/api/user/<user_id>/requests", methods=["GET"])
def api_get_user_requests(user_id):
    try:
        role = request.args.get("role", "seeker")
        results = get_user_access_requests(user_id, role)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requests_bp.route("/api/requests/<request_id>/status", methods=["PATCH"])
def api_update_status(request_id):
    try:
        data = request.get_json()
        update_access_request_status(request_id, data["status"])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@requests_bp.route("/api/requests/<request_id>/fee", methods=["PATCH"])
def api_update_fee(request_id):
    try:
        data = request.get_json()
        update_access_fee_payment_status(request_id, data["accessFeeStatus"])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@requests_bp.route("/api/requests/<request_id>/contact", methods=["POST"])
def api_release_contact(request_id):
    try:
        data = request.get_json()
        release_provider_contact(request_id, data["contactEmail"], data.get("contactPhone"))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


# ── Page Routes ──────────────────────────────────────────────

@requests_bp.route("/my-requests")
def my_requests_page():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    requests_list = get_user_access_requests(user["id"], user["role"])
    return render_template("requests/my_requests.html", user=user, requests=requests_list)


@requests_bp.route("/request/<request_id>", methods=["GET", "POST"])
def request_detail_page(request_id):
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    # Handle POST actions
    if request.method == "POST":
        action = request.form.get("action")

        if action == "approve":
            update_access_request_status(request_id, "approved")
        elif action == "reject":
            update_access_request_status(request_id, "rejected")
        elif action == "pay":
            update_access_fee_payment_status(request_id, "paid")
        elif action == "release":
            contact_email = request.form.get("contactEmail", "")
            contact_phone = request.form.get("contactPhone", "")

            # Collect all released benefit data from the form
            released_data = {}
            benefit_fields = {
                "video_call_link": ["video_call_link", "video_call_time"],
                "whatsapp_link": ["whatsapp_link"],
                "booked_chat": ["chat_platform", "chat_handle", "chat_time"],
                "appointment_details": ["appointment_type", "appointment_location", "appointment_time"],
                "digital_product": ["product_name", "product_url"],
                "exclusive_content": ["content_title", "content_url"],
                "shadowing_session": ["session_duration", "session_date", "session_location"],
                "network_fast_pass": ["contact_names", "intro_method"],
                "micro_consultation": ["consultation_duration", "consultation_notes"],
                "personalized_resources": ["resource_list"],
                "darkweb_access": ["darkweb_link", "darkweb_mirror_link", "darkweb_access_code", "darkweb_instructions"],
                "forex_exchange": ["forex_pair", "forex_rate", "forex_min_amount", "forex_contact_channel", "forex_terms"],
            }
            for benefit_key, fields in benefit_fields.items():
                if request.form.get(f"release_{benefit_key}"):
                    benefit_data = {}
                    for field in fields:
                        val = request.form.get(field, "").strip()
                        if val:
                            benefit_data[field] = val
                    if benefit_data:
                        released_data[benefit_key] = benefit_data

            release_provider_contact(
                request_id, contact_email, contact_phone or None,
                released_data=released_data if released_data else None
            )

        return redirect(url_for("requests.request_detail_page", request_id=request_id))

    req = get_access_request(request_id)
    if not req:
        return render_template("requests/request_detail.html", user=user, req=None)

    # Load dynamic split for display
    pct = get_current_provider_share_percentage()
    split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}
    return render_template("requests/request_detail.html", user=user, req=req, split=split)


@requests_bp.route("/submit-request/<provider_id>", methods=["POST"])
def submit_request(provider_id):
    """Handle access request submission from search page."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    purpose = request.form.get("purpose", "")
    if not purpose.strip():
        return redirect(url_for("providers.search_page"))

    result = create_access_request(user["id"], provider_id, purpose)
    return redirect(url_for("requests.request_detail_page", request_id=result["id"]))
