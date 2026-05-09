"""Provider service — CRUD operations for provider profiles."""

import uuid
import json
import os
from datetime import datetime, timezone
from flask import current_app
from app.database import get_db


# ── Verification Constants ──────────────────────────────
ALLOWED_DOC_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
ALLOWED_SELFIE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def create_provider_profile(user_id: str, title: str, bio: str, expertise: str,
                            phone_number: str, category: str, hourly_rate: float, access_fee: float,
                            offered_benefits: dict = None) -> dict:
    """Create a new provider profile."""
    db = get_db()
    provider_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    benefits_json = json.dumps(offered_benefits) if offered_benefits else None

    db.execute(
        """INSERT INTO providers (id, user_id, title, bio, expertise, phone_number, category,
           hourly_rate, access_fee, offered_benefits, request_approval_required, verified, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
        (provider_id, user_id, title, bio, expertise, phone_number, category,
         hourly_rate, access_fee, benefits_json, now, now),
    )
    db.commit()
    print(f"Provider profile created: {provider_id}")
    return {"id": provider_id, "userId": user_id, "title": title, "accessFee": access_fee, "verified": False}


def get_provider_by_user_id(user_id: str, requester_id: str = None) -> dict | None:
    """Get provider profile by user ID, optionally checking access for phone visibility."""
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE user_id = ?", (user_id,)).fetchone()
    if not provider:
        return None

    result = dict(provider)
    result = _normalize_provider(result)

    if not requester_id:
        result["phoneNumber"] = None
    else:
        has_access = check_seeker_access_to_provider(requester_id, result["id"])
        if not has_access:
            result["phoneNumber"] = None

    return result


def get_provider_by_id(provider_id: str, requester_id: str = None) -> dict | None:
    """Get provider profile by provider ID."""
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if not provider:
        return None

    result = _normalize_provider(dict(provider))

    if not requester_id:
        result["phoneNumber"] = None
    else:
        has_access = check_seeker_access_to_provider(requester_id, provider_id)
        if not has_access:
            result["phoneNumber"] = None

    return result


def check_seeker_access_to_provider(seeker_id: str, provider_id: str) -> bool:
    """Check if a seeker has paid + approved access to a provider."""
    db = get_db()
    row = db.execute(
        """SELECT id FROM access_requests
           WHERE seeker_id = ? AND provider_id = ? AND access_fee_status = 'paid' AND status = 'approved'""",
        (seeker_id, provider_id),
    ).fetchone()
    return row is not None


def search_providers(query: str = None, category: str = None, requester_id: str = None) -> list:
    """Search providers with optional keyword and category filters. Excludes suspended users."""
    db = get_db()

    sql = """SELECT p.* FROM providers p
             JOIN users u ON p.user_id = u.id
             WHERE COALESCE(u.status, 'active') != 'suspended'"""
    params = []

    if query:
        sql += " AND (p.title LIKE ? OR p.expertise LIKE ? OR p.bio LIKE ?)"
        like_query = f"%{query}%"
        params.extend([like_query, like_query, like_query])

    if category:
        sql += " AND p.category = ?"
        params.append(category)

    rows = db.execute(sql, params).fetchall()
    results = []

    for row in rows:
        provider = _normalize_provider(dict(row))

        # Get user's profile_pic
        user_row = db.execute("SELECT profile_pic FROM users WHERE id = ?", (provider['userId'],)).fetchone()
        if user_row and user_row['profile_pic']:
            provider['profilePhoto'] = user_row['profile_pic']

        if not requester_id:
            provider["phoneNumber"] = None
        else:
            has_access = check_seeker_access_to_provider(requester_id, provider["id"])
            if not has_access:
                provider["phoneNumber"] = None
        results.append(provider)

    print(f"Found {len(results)} providers")
    return results


def update_provider_profile(provider_id: str, updates: dict):
    """Update a provider profile with the given fields."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Build dynamic SET clause
    allowed_fields = {"title", "bio", "expertise", "phone_number", "category", "hourly_rate", "access_fee", "profile_photo"}
    set_parts = []
    params = []

    for key, value in updates.items():
        # Map camelCase to snake_case
        snake_key = _camel_to_snake(key)
        if snake_key in allowed_fields:
            set_parts.append(f"{snake_key} = ?")
            params.append(value)

    # Handle offered_benefits specially (JSON serialization)
    if "offeredBenefits" in updates or "offered_benefits" in updates:
        benefits = updates.get("offeredBenefits") or updates.get("offered_benefits")
        if isinstance(benefits, dict):
            set_parts.append("offered_benefits = ?")
            params.append(json.dumps(benefits))
        elif isinstance(benefits, str):
            set_parts.append("offered_benefits = ?")
            params.append(benefits)

    set_parts.append("updated_at = ?")
    params.append(now)
    params.append(provider_id)

    if set_parts:
        sql = f"UPDATE providers SET {', '.join(set_parts)} WHERE id = ?"
        db.execute(sql, params)
        db.commit()

    print(f"Provider profile updated: {provider_id}")


def _normalize_provider(row: dict) -> dict:
    """Convert snake_case DB row to camelCase for template compatibility."""
    # Deserialize offered_benefits JSON
    offered_benefits = {}
    raw_benefits = row.get("offered_benefits")
    if raw_benefits:
        try:
            offered_benefits = json.loads(raw_benefits) if isinstance(raw_benefits, str) else raw_benefits
        except (json.JSONDecodeError, TypeError):
            offered_benefits = {}

    return {
        "id": row["id"],
        "userId": row["user_id"],
        "title": row["title"],
        "bio": row["bio"],
        "expertise": row["expertise"],
        "phoneNumber": row["phone_number"],
        "hourlyRate": row["hourly_rate"],
        "accessFee": row["access_fee"],
        "requestApprovalRequired": bool(row["request_approval_required"]),
        "profilePhoto": row["profile_photo"],
        "category": row["category"],
        "offeredBenefits": offered_benefits,
        "verified": bool(row["verified"]),
        "verificationStatus": row.get("verification_status", "pending") or "pending",
        "idDocumentPath": row.get("id_document_path"),
        "selfiePath": row.get("selfie_path"),
        "verificationNotes": row.get("verification_notes"),
        "verificationSubmittedAt": row.get("verification_submitted_at"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


# ═══════════════════════════════════════════════════════════════
#  PROVIDER VERIFICATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _allowed_verification_file(filename, allowed_exts):
    """Check if a filename has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts


def save_verification_document(provider_id, file_obj, doc_type='id_document'):
    """Save an uploaded verification document to disk.

    Args:
        provider_id: The provider's ID.
        file_obj: The uploaded file object from Flask request.
        doc_type: 'id_document' or 'selfie'.

    Returns:
        The relative path to the saved file.

    Raises:
        ValueError: If file is invalid.
    """
    if not file_obj or file_obj.filename == '':
        raise ValueError(f"No {doc_type.replace('_', ' ')} file provided")

    allowed_exts = ALLOWED_DOC_EXTENSIONS if doc_type == 'id_document' else ALLOWED_SELFIE_EXTENSIONS
    if not _allowed_verification_file(file_obj.filename, allowed_exts):
        ext_list = ', '.join(allowed_exts).upper()
        raise ValueError(f"Invalid file format for {doc_type.replace('_', ' ')}. Accepted: {ext_list}")

    file_data = file_obj.read()
    if len(file_data) > MAX_FILE_SIZE:
        raise ValueError(f"File too large. Maximum size is 5MB.")

    if len(file_data) == 0:
        raise ValueError(f"Empty file uploaded for {doc_type.replace('_', ' ')}")

    # Create upload directory
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'verification_documents')
    os.makedirs(upload_dir, exist_ok=True)

    ext = file_obj.filename.rsplit('.', 1)[1].lower()
    filename = f"{provider_id}_{doc_type}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, 'wb') as f:
        f.write(file_data)

    relative_path = f"uploads/verification_documents/{filename}"
    print(f"Verification document saved: {relative_path}")
    return relative_path


def upload_verification_documents(provider_id, id_document_file=None, selfie_file=None):
    """Upload ID document and/or selfie for a provider.

    Updates the provider record with file paths.
    """
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if not provider:
        raise ValueError("Provider not found")

    updates = []
    params = []

    if id_document_file:
        # Delete old document if exists
        old_path = provider['id_document_path']
        if old_path:
            _delete_file_safely(old_path)
        path = save_verification_document(provider_id, id_document_file, 'id_document')
        updates.append("id_document_path = ?")
        params.append(path)

    if selfie_file:
        # Delete old selfie if exists
        old_path = provider['selfie_path']
        if old_path:
            _delete_file_safely(old_path)
        path = save_verification_document(provider_id, selfie_file, 'selfie')
        updates.append("selfie_path = ?")
        params.append(path)

    if updates:
        now = datetime.now(timezone.utc).isoformat()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(provider_id)
        sql = f"UPDATE providers SET {', '.join(updates)} WHERE id = ?"
        db.execute(sql, params)
        db.commit()

    return {"success": True, "providerId": provider_id}


def submit_verification(provider_id):
    """Submit a provider's verification request for admin review.

    Both id_document_path and selfie_path must be uploaded before submitting.
    Creates a verification_requests record and updates provider status to 'submitted'.
    """
    db = get_db()
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if not provider:
        raise ValueError("Provider not found")

    if not provider['id_document_path'] or not provider['selfie_path']:
        raise ValueError("Both ID document and selfie must be uploaded before submitting")

    if provider['verified']:
        raise ValueError("Provider is already verified")

    current_status = provider['verification_status'] or 'pending'
    if current_status == 'submitted':
        raise ValueError("Verification has already been submitted and is under review")

    now = datetime.now(timezone.utc).isoformat()
    request_id = str(uuid.uuid4())

    # Create verification request record
    db.execute(
        """INSERT INTO verification_requests (id, provider_id, id_document_path, selfie_path, submitted_at, status)
           VALUES (?, ?, ?, ?, ?, 'pending')""",
        (request_id, provider_id, provider['id_document_path'], provider['selfie_path'], now)
    )

    # Update provider verification status
    db.execute(
        "UPDATE providers SET verification_status = 'submitted', verification_submitted_at = ?, updated_at = ? WHERE id = ?",
        (now, now, provider_id)
    )
    db.commit()

    print(f"Verification submitted for provider {provider_id}, request {request_id}")
    return {"success": True, "requestId": request_id, "providerId": provider_id}


def get_provider_verification_status(provider_id):
    """Get the current verification status for a provider."""
    db = get_db()
    provider = db.execute(
        "SELECT id, verified, verification_status, id_document_path, selfie_path, verification_notes, verification_submitted_at FROM providers WHERE id = ?",
        (provider_id,)
    ).fetchone()
    if not provider:
        return None

    # Get latest verification request
    latest_request = db.execute(
        "SELECT * FROM verification_requests WHERE provider_id = ? ORDER BY submitted_at DESC LIMIT 1",
        (provider_id,)
    ).fetchone()

    return {
        "providerId": provider['id'],
        "verified": bool(provider['verified']),
        "verificationStatus": provider['verification_status'] or 'pending',
        "hasIdDocument": bool(provider['id_document_path']),
        "hasSelfie": bool(provider['selfie_path']),
        "idDocumentPath": provider['id_document_path'],
        "selfiePath": provider['selfie_path'],
        "verificationNotes": provider['verification_notes'],
        "submittedAt": provider['verification_submitted_at'],
        "latestRequest": dict(latest_request) if latest_request else None,
    }


def _delete_file_safely(relative_path):
    """Safely delete a file from the static uploads directory."""
    if not relative_path:
        return
    try:
        full_path = os.path.join(current_app.root_path, 'static', relative_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            print(f"Deleted file: {relative_path}")
    except OSError as e:
        print(f"Failed to delete file {relative_path}: {e}")


def delete_verification_documents(provider_id):
    """Delete uploaded verification documents for a provider (admin action post-verification)."""
    db = get_db()
    provider = db.execute("SELECT id_document_path, selfie_path FROM providers WHERE id = ?", (provider_id,)).fetchone()
    if not provider:
        raise ValueError("Provider not found")

    if provider['id_document_path']:
        _delete_file_safely(provider['id_document_path'])
    if provider['selfie_path']:
        _delete_file_safely(provider['selfie_path'])

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE providers SET id_document_path = NULL, selfie_path = NULL, updated_at = ? WHERE id = ?",
        (now, provider_id)
    )
    db.commit()
    print(f"Verification documents deleted for provider {provider_id}")
    return {"success": True}


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    import re
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
