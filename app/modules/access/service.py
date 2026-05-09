"""Access grants service — manage seeker-provider access links."""

import json
from app.database import get_db


def get_seeker_access_grants(seeker_id: str) -> list:
    """Get all active access grants for a seeker (their linked providers)."""
    db = get_db()
    grants = db.execute(
        "SELECT * FROM access_grants WHERE seeker_id = ? AND status = 'active' ORDER BY granted_at DESC",
        (seeker_id,),
    ).fetchall()

    results = []
    for grant in grants:
        grant = dict(grant)
        provider = db.execute(
            "SELECT title, expertise, category, user_id FROM providers WHERE id = ?",
            (grant["provider_id"],),
        ).fetchone()

        provider_user = None
        if provider:
            provider_user = db.execute(
                "SELECT first_name, last_name FROM users WHERE id = ?",
                (provider["user_id"],),
            ).fetchone()

        # Deserialize granted_data JSON
        granted_data = {}
        raw_granted = grant.get("granted_data")
        if raw_granted:
            try:
                granted_data = json.loads(raw_granted) if isinstance(raw_granted, str) else raw_granted
            except (json.JSONDecodeError, TypeError):
                granted_data = {}

        results.append({
            "id": grant["id"],
            "seekerId": grant["seeker_id"],
            "providerId": grant["provider_id"],
            "requestId": grant["request_id"],
            "contactEmail": grant["contact_email"],
            "contactPhone": grant["contact_phone"],
            "grantedData": granted_data,
            "grantedAt": grant["granted_at"],
            "expiresAt": grant["expires_at"],
            "status": grant["status"],
            "providerTitle": provider["title"] if provider else "Unknown",
            "providerExpertise": provider["expertise"] if provider else "",
            "providerCategory": provider["category"] if provider else "",
            "providerName": f"{provider_user['first_name']} {provider_user['last_name']}" if provider_user else "Unknown",
        })

    return results


def get_provider_access_grants(provider_user_id: str) -> list:
    """Get all seekers who have been granted access to a provider."""
    db = get_db()
    provider_profile = db.execute("SELECT id FROM providers WHERE user_id = ?", (provider_user_id,)).fetchone()
    if not provider_profile:
        return []

    grants = db.execute(
        "SELECT * FROM access_grants WHERE provider_id = ? AND status = 'active' ORDER BY granted_at DESC",
        (provider_profile["id"],),
    ).fetchall()

    results = []
    for grant in grants:
        grant = dict(grant)
        seeker = db.execute(
            "SELECT first_name, last_name, email FROM users WHERE id = ?",
            (grant["seeker_id"],),
        ).fetchone()

        # Deserialize granted_data JSON for provider view too
        granted_data_prov = {}
        raw_granted_prov = grant.get("granted_data")
        if raw_granted_prov:
            try:
                granted_data_prov = json.loads(raw_granted_prov) if isinstance(raw_granted_prov, str) else raw_granted_prov
            except (json.JSONDecodeError, TypeError):
                granted_data_prov = {}

        results.append({
            "id": grant["id"],
            "seekerId": grant["seeker_id"],
            "providerId": grant["provider_id"],
            "requestId": grant["request_id"],
            "contactEmail": grant["contact_email"],
            "contactPhone": grant["contact_phone"],
            "grantedData": granted_data_prov,
            "grantedAt": grant["granted_at"],
            "expiresAt": grant["expires_at"],
            "status": grant["status"],
            "seekerName": f"{seeker['first_name']} {seeker['last_name']}" if seeker else "Unknown",
            "seekerEmail": seeker["email"] if seeker else "",
        })

    return results
