"""Reviews & Trust Score service — verified transaction-based reviews.

This is what differentiates ThirdParty Access from LinkedIn:
- Every review is backed by a verified payment (no fake reviews)
- Trust scores are calculated from real completed transactions
- Seekers can only review after paying and completing an access grant
"""

import uuid
from datetime import datetime, timezone
from app.database import get_db
from app.modules.notifications.service import create_notification


def submit_review(request_id: str, reviewer_id: str, provider_id: str,
                  rating: int, comment: str = None) -> dict:
    """Submit a review for a completed and paid access request.

    Only seekers who have paid and received access can leave reviews.
    """
    db = get_db()

    # Validate rating
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise ValueError("Rating must be between 1 and 5")

    # Validate comment
    if comment:
        comment = comment.strip()[:500]  # Max 500 chars
        if not comment:
            comment = None

    # Check that the access request exists, is completed, and is paid
    req = db.execute(
        """SELECT * FROM access_requests
           WHERE id = ? AND seeker_id = ? AND provider_id = ?
           AND access_fee_status = 'paid'""",
        (request_id, reviewer_id, provider_id),
    ).fetchone()
    if not req:
        raise ValueError("You can only review after a completed, paid transaction")

    # Check for duplicate review
    existing = db.execute(
        "SELECT id FROM reviews WHERE request_id = ? AND reviewer_id = ?",
        (request_id, reviewer_id),
    ).fetchone()
    if existing:
        raise ValueError("You have already reviewed this transaction")

    review_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO reviews (id, request_id, reviewer_id, provider_id, rating, comment, is_verified_transaction, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
        (review_id, request_id, reviewer_id, provider_id, rating, comment, now),
    )
    db.commit()

    # Notify the provider
    reviewer = db.execute("SELECT first_name, last_name FROM users WHERE id = ?", (reviewer_id,)).fetchone()
    reviewer_name = f"{reviewer['first_name']} {reviewer['last_name']}" if reviewer else "A seeker"

    provider = db.execute("SELECT user_id FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if provider:
        stars = rating * "*"
        create_notification(
            provider["user_id"], "new_review", "New Review Received!",
            f"{reviewer_name} left a {rating}-star review for your profile.",
            request_id,
        )

    print(f"Review submitted: {review_id}, provider={provider_id}, rating={rating}")
    return {"id": review_id, "rating": rating, "comment": comment}


def get_provider_reviews(provider_id: str) -> list:
    """Get all reviews for a provider, newest first."""
    db = get_db()
    rows = db.execute(
        """SELECT r.*, u.first_name, u.last_name
           FROM reviews r
           JOIN users u ON r.reviewer_id = u.id
           WHERE r.provider_id = ?
           ORDER BY r.created_at DESC""",
        (provider_id,),
    ).fetchall()

    return [_normalize_review(dict(row)) for row in rows]


def get_provider_trust_score(provider_id: str) -> dict:
    """Calculate the trust score for a provider.

    Trust Score formula:
    - Base: Average rating (1-5 scale, converted to 0-100)
    - Bonus: +2 points per verified review (up to +20)
    - Minimum 3 reviews needed for a public score

    Returns score (0-100), totalReviews, averageRating, breakdown.
    """
    db = get_db()

    stats = db.execute(
        """SELECT COUNT(*) as total, AVG(rating) as avg_rating,
                  SUM(CASE WHEN rating = 5 THEN 1 ELSE 0 END) as five_star,
                  SUM(CASE WHEN rating = 4 THEN 1 ELSE 0 END) as four_star,
                  SUM(CASE WHEN rating = 3 THEN 1 ELSE 0 END) as three_star,
                  SUM(CASE WHEN rating = 2 THEN 1 ELSE 0 END) as two_star,
                  SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as one_star
           FROM reviews WHERE provider_id = ?""",
        (provider_id,),
    ).fetchone()

    total = stats["total"] or 0
    avg_rating = stats["avg_rating"] or 0

    if total < 1:
        return {
            "score": 0,
            "totalReviews": 0,
            "averageRating": 0,
            "hasEnoughReviews": False,
            "breakdown": {"fiveStar": 0, "fourStar": 0, "threeStar": 0, "twoStar": 0, "oneStar": 0},
        }

    # Calculate trust score: avg rating scaled to 100 + volume bonus
    base_score = (avg_rating / 5) * 80  # max 80 from ratings
    volume_bonus = min(total * 2, 20)  # +2 per review, max +20
    trust_score = min(100, round(base_score + volume_bonus))

    return {
        "score": trust_score,
        "totalReviews": total,
        "averageRating": round(avg_rating, 1),
        "hasEnoughReviews": total >= 3,
        "breakdown": {
            "fiveStar": stats["five_star"] or 0,
            "fourStar": stats["four_star"] or 0,
            "threeStar": stats["three_star"] or 0,
            "twoStar": stats["two_star"] or 0,
            "oneStar": stats["one_star"] or 0,
        },
    }


def can_review(request_id: str, reviewer_id: str) -> bool:
    """Check if a seeker can leave a review for a given request."""
    db = get_db()

    # Must be a paid, completed or approved request
    req = db.execute(
        """SELECT id FROM access_requests
           WHERE id = ? AND seeker_id = ? AND access_fee_status = 'paid'""",
        (request_id, reviewer_id),
    ).fetchone()
    if not req:
        return False

    # Must not have already reviewed
    existing = db.execute(
        "SELECT id FROM reviews WHERE request_id = ? AND reviewer_id = ?",
        (request_id, reviewer_id),
    ).fetchone()
    return existing is None


def _normalize_review(row: dict) -> dict:
    """Convert review DB row to camelCase dict."""
    return {
        "id": row["id"],
        "requestId": row["request_id"],
        "reviewerId": row["reviewer_id"],
        "providerId": row["provider_id"],
        "rating": row["rating"],
        "comment": row["comment"],
        "isVerifiedTransaction": bool(row["is_verified_transaction"]),
        "reviewerName": f"{row['first_name']} {row['last_name']}",
        "createdAt": row["created_at"],
    }
