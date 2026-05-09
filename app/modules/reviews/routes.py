"""Reviews routes — API + page routes for the Verified Trust Score system."""

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session

from app.modules.reviews.service import (
    submit_review, get_provider_reviews, get_provider_trust_score, can_review,
)

reviews_bp = Blueprint("reviews", __name__)


# ── API Endpoints ──────────────────────────────────────────────

@reviews_bp.route("/api/reviews/provider/<provider_id>", methods=["GET"])
def api_get_provider_reviews(provider_id):
    """Get all reviews for a provider."""
    try:
        reviews = get_provider_reviews(provider_id)
        return jsonify(reviews)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@reviews_bp.route("/api/reviews/trust-score/<provider_id>", methods=["GET"])
def api_get_trust_score(provider_id):
    """Get the trust score for a provider."""
    try:
        score = get_provider_trust_score(provider_id)
        return jsonify(score)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@reviews_bp.route("/api/reviews/can-review/<request_id>", methods=["GET"])
def api_can_review(request_id):
    """Check if current user can review a request."""
    user = session.get("user")
    if not user:
        return jsonify({"canReview": False})
    return jsonify({"canReview": can_review(request_id, user["id"])})


@reviews_bp.route("/api/reviews", methods=["POST"])
def api_submit_review():
    """Submit a new review (API endpoint)."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Not authenticated"}), 401

    try:
        data = request.get_json()
        result = submit_review(
            data["requestId"], user["id"], data["providerId"],
            int(data["rating"]), data.get("comment"),
        )
        return jsonify(result)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


# ── Page Routes ────────────────────────────────────────────────

@reviews_bp.route("/review/<request_id>", methods=["GET", "POST"])
def review_page(request_id):
    """Review form page — accessible after a paid access request."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    from app.modules.requests.service import get_access_request
    req = get_access_request(request_id)
    if not req:
        return render_template("reviews/review.html", user=user, req=None, error="Request not found")

    if not can_review(request_id, user["id"]):
        return render_template("reviews/review.html", user=user, req=req,
                               error="You cannot review this transaction (already reviewed or not eligible)")

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating", 0))
            comment = request.form.get("comment", "").strip()
            submit_review(request_id, user["id"], req["providerId"], rating, comment or None)
            return redirect(url_for("reviews.review_success_page", request_id=request_id))
        except ValueError as e:
            return render_template("reviews/review.html", user=user, req=req, error=str(e))

    return render_template("reviews/review.html", user=user, req=req, error=None)


@reviews_bp.route("/review/<request_id>/success")
def review_success_page(request_id):
    """Thank-you page after submitting a review."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    from app.modules.requests.service import get_access_request
    req = get_access_request(request_id)
    return render_template("reviews/review_success.html", user=user, req=req)


@reviews_bp.route("/provider/<provider_id>/reviews")
def provider_reviews_page(provider_id):
    """View all reviews and trust score for a provider."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    from app.modules.providers.service import get_provider_by_id
    provider = get_provider_by_id(provider_id, user.get("id"))
    if not provider:
        return redirect(url_for("providers.search_page"))

    reviews = get_provider_reviews(provider_id)
    trust_score = get_provider_trust_score(provider_id)

    return render_template("reviews/provider_reviews.html",
                           user=user, provider=provider, reviews=reviews, trust_score=trust_score)
