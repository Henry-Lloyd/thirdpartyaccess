"""Notification routes — API endpoints for notification operations."""

from flask import Blueprint, request, jsonify, session

from app.modules.notifications.service import (
    get_user_notifications, get_unread_notification_count,
    mark_notification_as_read, mark_all_notifications_as_read,
    delete_notification, create_notification,
)

notifications_bp = Blueprint("notifications", __name__)


# ── API Endpoints ──────────────────────────────────────────────

@notifications_bp.route("/api/notifications/<user_id>", methods=["GET"])
def api_get_notifications(user_id):
    try:
        notifications = get_user_notifications(user_id)
        return jsonify(notifications)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@notifications_bp.route("/api/notifications/<user_id>/unread-count", methods=["GET"])
def api_unread_count(user_id):
    try:
        count = get_unread_notification_count(user_id)
        return jsonify({"count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@notifications_bp.route("/api/notifications/<notification_id>/read", methods=["PATCH"])
def api_mark_as_read(notification_id):
    try:
        mark_notification_as_read(notification_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.route("/api/notifications/<user_id>/read-all", methods=["PATCH"])
def api_mark_all_as_read(user_id):
    try:
        mark_all_notifications_as_read(user_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.route("/api/notifications/<notification_id>", methods=["DELETE"])
def api_delete_notification(notification_id):
    try:
        delete_notification(notification_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@notifications_bp.route("/api/notifications", methods=["POST"])
def api_create_notification():
    try:
        data = request.get_json()
        notification = create_notification(
            data["userId"], data["type"], data["title"],
            data["message"], data.get("relatedRequestId")
        )
        return jsonify(notification)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
