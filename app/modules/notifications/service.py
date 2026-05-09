"""Notification service — create, read, mark, delete notifications."""

import uuid
from datetime import datetime, timezone
from app.database import get_db


def create_notification(user_id: str, notif_type: str, title: str, message: str, related_request_id: str = None) -> dict:
    """Create a new notification for a user."""
    db = get_db()
    notification_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO notifications (id, user_id, type, title, message, related_request_id, is_read, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (notification_id, user_id, notif_type, title, message, related_request_id, now),
    )
    db.commit()
    print(f"Notification created: {notification_id} for user {user_id}")
    return {"id": notification_id}


def get_user_notifications(user_id: str) -> list:
    """Get all notifications for a user, newest first."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [_normalize_notification(dict(row)) for row in rows]


def get_unread_notification_count(user_id: str) -> int:
    """Count unread notifications for a user."""
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM notifications WHERE user_id = ? AND is_read = 0",
        (user_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def mark_notification_as_read(notification_id: str):
    """Mark a single notification as read."""
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    db.commit()
    print(f"Notification marked as read: {notification_id}")


def mark_all_notifications_as_read(user_id: str):
    """Mark all notifications for a user as read."""
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
    db.commit()
    print(f"All notifications marked as read for user {user_id}")


def delete_notification(notification_id: str):
    """Delete a notification."""
    db = get_db()
    db.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    db.commit()
    print(f"Notification deleted: {notification_id}")


def _normalize_notification(row: dict) -> dict:
    """Convert snake_case DB row to camelCase."""
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "type": row["type"],
        "title": row["title"],
        "message": row["message"],
        "relatedRequestId": row["related_request_id"],
        "isRead": row["is_read"],
        "createdAt": row["created_at"],
    }
