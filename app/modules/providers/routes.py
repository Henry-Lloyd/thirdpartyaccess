"""Provider routes — API + page routes for provider operations."""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session

from app.modules.providers.service import (
    create_provider_profile, get_provider_by_user_id, get_provider_by_id,
    search_providers, update_provider_profile, check_seeker_access_to_provider,
    upload_verification_documents, submit_verification, get_provider_verification_status
)
from app.modules.payments.service import get_current_provider_share_percentage

providers_bp = Blueprint("providers", __name__)


# ── API Endpoints ──────────────────────────────────────────────

@providers_bp.route("/api/providers", methods=["POST"])
def api_create_provider():
    try:
        data = request.get_json()
        provider = create_provider_profile(
            data["userId"], data["title"], data["bio"], data["expertise"],
            data["phoneNumber"], data["category"],
            float(data.get("hourlyRate", 0)), float(data.get("accessFee", 0))
        )
        return jsonify(provider)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@providers_bp.route("/api/providers/search", methods=["GET"])
def api_search_providers():
    try:
        query = request.args.get("q")
        category = request.args.get("category")
        requester_id = request.args.get("requesterId")
        providers = search_providers(query, category, requester_id)
        return jsonify(providers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@providers_bp.route("/api/providers/<provider_id>", methods=["GET"])
def api_get_provider(provider_id):
    try:
        requester_id = request.args.get("requesterId")
        provider = get_provider_by_id(provider_id, requester_id)
        if not provider:
            return jsonify({"error": "Provider not found"}), 404
        return jsonify(provider)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@providers_bp.route("/api/providers/user/<user_id>", methods=["GET"])
def api_get_provider_by_user(user_id):
    try:
        provider = get_provider_by_user_id(user_id)
        if not provider:
            return jsonify({"error": "Provider not found"}), 404
        return jsonify(provider)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@providers_bp.route("/api/providers/<provider_id>", methods=["PUT"])
def api_update_provider(provider_id):
    try:
        data = request.get_json()
        update_provider_profile(provider_id, data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@providers_bp.route("/api/access/check/<seeker_id>/<provider_id>", methods=["GET"])
def api_check_access(seeker_id, provider_id):
    try:
        has_access = check_seeker_access_to_provider(seeker_id, provider_id)
        return jsonify({"hasAccess": has_access})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Verification API Endpoints ───────────────────────────────

@providers_bp.route("/api/provider/verify/upload", methods=["POST"])
def api_verify_upload():
    """Upload ID document and/or selfie for verification."""
    user = session.get("user")
    if not user or user.get("role") != "provider":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        provider = get_provider_by_user_id(user["id"])
        if not provider:
            return jsonify({"error": "Provider profile not found"}), 404

        id_doc = request.files.get("id_document")
        selfie = request.files.get("selfie")

        if not id_doc and not selfie:
            return jsonify({"error": "At least one file (ID document or selfie) is required"}), 400

        result = upload_verification_documents(provider["id"], id_doc, selfie)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@providers_bp.route("/api/provider/verify/submit", methods=["POST"])
def api_verify_submit():
    """Submit verification request for admin review."""
    user = session.get("user")
    if not user or user.get("role") != "provider":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        provider = get_provider_by_user_id(user["id"])
        if not provider:
            return jsonify({"error": "Provider profile not found"}), 404

        result = submit_verification(provider["id"])
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@providers_bp.route("/api/provider/verify/status", methods=["GET"])
def api_verify_status():
    """Get the current verification status for the logged-in provider."""
    user = session.get("user")
    if not user or user.get("role") != "provider":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        provider = get_provider_by_user_id(user["id"])
        if not provider:
            return jsonify({"error": "Provider profile not found"}), 404

        status = get_provider_verification_status(provider["id"])
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Verification Page Route ──────────────────────────────────

@providers_bp.route("/provider/verify", methods=["GET", "POST"])
def verify_page():
    """Provider verification page - upload documents & submit for review."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))
    if user.get("role") != "provider":
        return redirect(url_for("main.dashboard"))

    provider = get_provider_by_user_id(user["id"])
    if not provider:
        return redirect(url_for("providers.setup_page"))

    error = None
    success = None
    verification = get_provider_verification_status(provider["id"])

    if request.method == "POST":
        action = request.form.get("action", "upload")
        try:
            if action == "upload":
                id_doc = request.files.get("id_document")
                selfie = request.files.get("selfie")
                if not id_doc and not selfie:
                    raise ValueError("Please select at least one file to upload.")
                upload_verification_documents(provider["id"], id_doc, selfie)
                success = "Documents uploaded successfully."
            elif action == "submit":
                submit_verification(provider["id"])
                success = "Verification submitted! Our Team shall review your documents shortly."
            # Refresh status
            verification = get_provider_verification_status(provider["id"])
        except ValueError as e:
            error = str(e)

    return render_template("providers/verify.html", user=user, provider=provider,
                           verification=verification, error=error, success=success)


# ── Page Routes ──────────────────────────────────────────────

@providers_bp.route("/provider-setup", methods=["GET", "POST"])
def setup_page():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if request.method == "POST":
        try:
            # Collect offered benefits from checkboxes
            benefit_types = [
                "video_call_link", "whatsapp_link", "booked_chat",
                "appointment_details", "digital_product", "exclusive_content",
                "shadowing_session", "network_fast_pass",
                "micro_consultation", "personalized_resources",
                "darkweb_access", "forex_exchange"
            ]
            offered_benefits = {}
            for bt in benefit_types:
                if request.form.get(f"benefit_{bt}"):
                    offered_benefits[bt] = True

            create_provider_profile(
                user["id"],
                request.form.get("title", ""),
                request.form.get("bio", ""),
                request.form.get("expertise", ""),
                request.form.get("phoneNumber", ""),
                request.form.get("category", ""),
                float(request.form.get("hourlyRate", 0) or 0),
                float(request.form.get("accessFee", 0) or 0),
                offered_benefits=offered_benefits if offered_benefits else None,
            )
            return redirect(url_for("main.dashboard"))
        except (ValueError, Exception) as e:
            pct = get_current_provider_share_percentage()
            split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}
            return render_template("providers/setup.html", user=user, error=str(e), split=split)

    pct = get_current_provider_share_percentage()
    split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}
    return render_template("providers/setup.html", user=user, error=None, split=split)


@providers_bp.route("/search")
def search_page():
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    query = request.args.get("q", "")
    providers = search_providers(query, requester_id=user.get("id"))
    return render_template("providers/search.html", user=user, providers=providers, query=query)
