"""Request service — access request workflow (create, approve, pay, release)."""

import uuid
import json
from datetime import datetime, timezone
from app.database import get_db
from app.modules.notifications.service import create_notification
from app.modules.payments.service import get_current_provider_share_percentage


def create_access_request(seeker_id: str, provider_id: str, purpose: str) -> dict:
    """Submit a new access request from a seeker to a provider."""
    db = get_db()
    request_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO access_requests
           (id, seeker_id, provider_id, purpose, status, access_fee_status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'pending', 'pending', ?, ?)""",
        (request_id, seeker_id, provider_id, purpose, now, now),
    )
    db.commit()

    # Notify the provider
    provider = db.execute("SELECT user_id, title FROM providers WHERE id = ?", (provider_id,)).fetchone()
    seeker = db.execute("SELECT first_name, last_name FROM users WHERE id = ?", (seeker_id,)).fetchone()

    if provider:
        seeker_name = f"{seeker['first_name']} {seeker['last_name']}" if seeker else "A seeker"
        create_notification(
            provider["user_id"], "new_request", "New Access Request",
            f"{seeker_name} has requested access to your contact details.",
            request_id,
        )

    print(f"Access request created: {request_id}")
    return {"id": request_id, "status": "pending"}


def get_access_request(request_id: str) -> dict | None:
    """Get a single request with enriched seeker/provider details."""
    db = get_db()
    req = db.execute("SELECT * FROM access_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        return None

    req = dict(req)
    seeker = db.execute("SELECT first_name, last_name, email FROM users WHERE id = ?", (req["seeker_id"],)).fetchone()
    provider = db.execute("SELECT title, user_id, access_fee FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()

    provider_user = None
    if provider:
        provider_user = db.execute("SELECT first_name, last_name FROM users WHERE id = ?", (provider["user_id"],)).fetchone()

    # Check for split info from payments table
    payment = db.execute(
        "SELECT platform_share, provider_share, split_percentage FROM payments WHERE request_id = ? AND status = 'success' LIMIT 1",
        (request_id,),
    ).fetchone()

    # Deserialize released_data JSON
    released_data = {}
    raw_released = req.get("released_data")
    if raw_released:
        try:
            released_data = json.loads(raw_released) if isinstance(raw_released, str) else raw_released
        except (json.JSONDecodeError, TypeError):
            released_data = {}

    # Load provider's offered_benefits for the release form
    provider_benefits = {}
    if provider:
        prov_full = db.execute("SELECT offered_benefits FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()
        if prov_full and prov_full["offered_benefits"]:
            try:
                provider_benefits = json.loads(prov_full["offered_benefits"])
            except (json.JSONDecodeError, TypeError):
                provider_benefits = {}

    result = {
        "id": req["id"],
        "seekerId": req["seeker_id"],
        "providerId": req["provider_id"],
        "purpose": req["purpose"],
        "status": req["status"],
        "contactEmail": req["contact_email"],
        "contactPhone": req["contact_phone"],
        "releasedData": released_data,
        "providerBenefits": provider_benefits,
        "accessFeeStatus": req["access_fee_status"],
        "paymentMethod": req["payment_method"],
        "transactionId": req["transaction_id"],
        "createdAt": req["created_at"],
        "updatedAt": req["updated_at"],
        "seekerName": f"{seeker['first_name']} {seeker['last_name']}" if seeker else "Unknown",
        "seekerEmail": seeker["email"] if seeker else "",
        "providerTitle": provider["title"] if provider else "Unknown",
        "providerName": f"{provider_user['first_name']} {provider_user['last_name']}" if provider_user else "Unknown",
        "accessFee": provider["access_fee"] if provider else 0,
        "platformShare": payment["platform_share"] if payment else 0,
        "providerShare": payment["provider_share"] if payment else 0,
        "splitPercentage": payment["split_percentage"] if payment else get_current_provider_share_percentage(),
    }
    return result


def get_user_access_requests(user_id: str, role: str) -> list:
    """Get all requests for a user (either as seeker or provider)."""
    db = get_db()

    if role == "seeker":
        rows = db.execute(
            "SELECT * FROM access_requests WHERE seeker_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()

        results = []
        for row in rows:
            row = dict(row)
            provider = db.execute("SELECT title, access_fee FROM providers WHERE id = ?", (row["provider_id"],)).fetchone()
            results.append({
                **_normalize_request(row),
                "providerTitle": provider["title"] if provider else "Unknown",
                "accessFee": provider["access_fee"] if provider else 0,
            })
        return results
    else:
        # Provider role — find their provider profile first
        provider_profile = db.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not provider_profile:
            return []

        rows = db.execute(
            "SELECT * FROM access_requests WHERE provider_id = ? ORDER BY created_at DESC",
            (provider_profile["id"],),
        ).fetchall()

        results = []
        for row in rows:
            row = dict(row)
            seeker = db.execute("SELECT first_name, last_name, email FROM users WHERE id = ?", (row["seeker_id"],)).fetchone()
            results.append({
                **_normalize_request(row),
                "seekerName": f"{seeker['first_name']} {seeker['last_name']}" if seeker else "Unknown",
                "seekerEmail": seeker["email"] if seeker else "",
            })
        return results


def update_access_request_status(request_id: str, status: str):
    """Approve or reject a request."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    req = db.execute("SELECT seeker_id, provider_id FROM access_requests WHERE id = ?", (request_id,)).fetchone()
    db.execute("UPDATE access_requests SET status = ?, updated_at = ? WHERE id = ?", (status, now, request_id))
    db.commit()

    # Notify seeker
    if req:
        provider = db.execute("SELECT title FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()
        provider_title = provider["title"] if provider else "A provider"

        if status == "approved":
            create_notification(
                req["seeker_id"], "request_approved", "Request Approved!",
                f"{provider_title} has approved your access request. Please proceed with the access fee payment.",
                request_id,
            )
        elif status == "rejected":
            create_notification(
                req["seeker_id"], "request_rejected", "Request Rejected",
                f"{provider_title} has declined your access request.",
                request_id,
            )

    print(f"Access request updated: {request_id} -> {status}")


def update_access_fee_payment_status(request_id: str, access_fee_status: str):
    """Record that the seeker has paid the access fee."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    req = db.execute("SELECT seeker_id, provider_id FROM access_requests WHERE id = ?", (request_id,)).fetchone()
    db.execute("UPDATE access_requests SET access_fee_status = ?, updated_at = ? WHERE id = ?",
               (access_fee_status, now, request_id))
    db.commit()

    if req and access_fee_status == "paid":
        seeker = db.execute("SELECT first_name, last_name FROM users WHERE id = ?", (req["seeker_id"],)).fetchone()
        seeker_name = f"{seeker['first_name']} {seeker['last_name']}" if seeker else "A seeker"
        provider = db.execute("SELECT user_id, title FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()

        if provider:
            create_notification(
                provider["user_id"], "payment_received", "Payment Received!",
                f"{seeker_name} has paid the access fee. You can now release your contact details.",
                request_id,
            )

        create_notification(
            req["seeker_id"], "payment_received", "Payment Successful",
            f"Your payment has been processed. {provider['title'] if provider else 'The provider'} will release their contact details shortly.",
            request_id,
        )

    print(f"Access fee updated: {request_id} -> {access_fee_status}")


def release_provider_contact(request_id: str, contact_email: str, contact_phone: str = None, released_data: dict = None):
    """Provider releases their contact info + benefits — creates a permanent access grant."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    released_data_json = json.dumps(released_data) if released_data else None

    req = db.execute("SELECT seeker_id, provider_id FROM access_requests WHERE id = ?", (request_id,)).fetchone()

    db.execute(
        "UPDATE access_requests SET contact_email = ?, contact_phone = ?, released_data = ?, status = 'completed', updated_at = ? WHERE id = ?",
        (contact_email, contact_phone, released_data_json, now, request_id),
    )

    if req:
        grant_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO access_grants (id, seeker_id, provider_id, request_id, contact_email, contact_phone, granted_data, granted_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (grant_id, req["seeker_id"], req["provider_id"], request_id, contact_email, contact_phone, released_data_json, now),
        )
        db.commit()
        print(f"Access grant created: {grant_id}")

        # Build a richer notification message listing released benefits
        provider = db.execute("SELECT title FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()
        prov_title = provider['title'] if provider else 'The provider'
        benefit_count = len(released_data) if released_data else 0
        if benefit_count > 0:
            msg = f"{prov_title} has released contact details and {benefit_count} additional benefit(s). Check your \"Value Vault\" to view everything."
        else:
            msg = f"{prov_title} has released their contact details. Check your \"Value Vault\" to view them."
        create_notification(
            req["seeker_id"], "access_granted", "Benefits Released!",
            msg, request_id,
        )
    else:
        db.commit()

    print(f"Contact released for request: {request_id}")


def _normalize_request(row: dict) -> dict:
    """Convert snake_case DB row to camelCase."""
    return {
        "id": row["id"],
        "seekerId": row["seeker_id"],
        "providerId": row["provider_id"],
        "purpose": row["purpose"],
        "status": row["status"],
        "contactEmail": row["contact_email"],
        "contactPhone": row["contact_phone"],
        "accessFeeStatus": row["access_fee_status"],
        "paymentMethod": row["payment_method"],
        "transactionId": row["transaction_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
