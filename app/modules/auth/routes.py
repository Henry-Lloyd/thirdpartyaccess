"""Authentication routes — login, register, switch role, get user (API + page routes)."""

import os
import uuid
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash, current_app

from app.modules.auth.service import (
    register_user, login_user, get_user_by_id, switch_role,
    request_password_reset, verify_reset_token, reset_password,
)

auth_bp = Blueprint("auth", __name__)


# -- API Endpoints -------------------------------------------------------

@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    try:
        data = request.get_json(silent=True) or {}
        required_fields = ["email", "password", "firstName", "lastName", "role"]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        user = register_user(
            data["email"], data["password"],
            data["firstName"], data["lastName"], data["role"]
        )
        return jsonify(user)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
        required_fields = ["email", "password", "role"]
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        ip_address = request.remote_addr or "unknown"
        user = login_user(data["email"], data["password"], data["role"], ip_address)
        return jsonify(user)
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 401


@auth_bp.route("/api/auth/user/<user_id>", methods=["GET"])
def api_get_user(user_id):
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)


# -- Page Routes ---------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    """Login page — user selects their role (seeker or provider) before logging in."""
    role = request.args.get("role", "seeker")

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        role = request.form.get("role", "seeker")
        ip_address = request.remote_addr or "unknown"

        try:
            user = login_user(email, password, role, ip_address)
            session["user"] = user
            session.permanent = True
            if role == "provider":
                return redirect(url_for("main.dashboard"))
            return redirect(url_for("main.dashboard"))
        except ValueError as e:
            return render_template("auth/login.html", error=str(e), email=email, role=role)

    return render_template("auth/login.html", error=None, email="", role=role)


@auth_bp.route("/register", methods=["GET", "POST"])
def register_page():
    role = request.args.get("role", "seeker")

    if request.method == "POST":
        first_name = request.form.get("firstName", "")
        last_name = request.form.get("lastName", "")
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirmPassword", "")
        role = request.form.get("role", "seeker")

        if password != confirm_password:
            return render_template("auth/register.html", error="Passwords do not match", role=role,
                                   firstName=first_name, lastName=last_name, email=email)

        try:
            user = register_user(email, password, first_name, last_name, role)
            session["user"] = user
            session.permanent = True
            if role == "provider":
                return redirect(url_for("providers.setup_page"))
            return redirect(url_for("main.dashboard"))
        except ValueError as e:
            return render_template("auth/register.html", error=str(e), role=role,
                                   firstName=first_name, lastName=last_name, email=email)

    return render_template("auth/register.html", error=None, role=role,
                           firstName="", lastName="", email="")


@auth_bp.route("/switch-role")
def switch_role_page():
    """Switch to the other role for the same email (no password re-entry)."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    target_role = "provider" if user["role"] == "seeker" else "seeker"

    try:
        new_user = switch_role(user["email"], target_role)
        session["user"] = new_user
        return redirect(url_for("main.dashboard"))
    except ValueError:
        # User doesn't have the other role — redirect to register for that role
        return redirect(url_for("auth.register_page", role=target_role))


# -- Password Reset Routes -----------------------------------------------

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_page():
    """Forgot password page — user enters email + role to receive a reset token."""
    role = request.args.get("role", "seeker")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "seeker")

        if not email:
            return render_template("auth/forgot_password.html", error="Please enter your email address.", role=role, email="")

        try:
            result = request_password_reset(email, role)
            # Show the reset link/token to the user directly
            # (In production, this would be sent via email instead)
            return render_template("auth/forgot_password.html",
                                   success=True, reset_token=result["token"],
                                   email=result["email"], role=result["role"])
        except ValueError as e:
            # For security we show a generic message whether account exists or not
            return render_template("auth/forgot_password.html",
                                   success=True, reset_token=None,
                                   email=email, role=role)

    return render_template("auth/forgot_password.html", error=None, role=role, email="", success=False)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    """Reset password page — user sets a new password using their reset token."""
    token = request.args.get("token", "")

    if request.method == "POST":
        token = request.form.get("token", "")
        new_password = request.form.get("password", "")
        confirm_password = request.form.get("confirmPassword", "")

        if new_password != confirm_password:
            token_info = verify_reset_token(token)
            return render_template("auth/reset_password.html",
                                   error="Passwords do not match.", token=token,
                                   token_valid=token_info is not None,
                                   token_info=token_info)

        try:
            result = reset_password(token, new_password)
            return render_template("auth/reset_password.html",
                                   success=True, email=result["email"],
                                   role=result["role"], token="", token_valid=False)
        except ValueError as e:
            token_info = verify_reset_token(token)
            return render_template("auth/reset_password.html",
                                   error=str(e), token=token,
                                   token_valid=token_info is not None,
                                   token_info=token_info)

    # GET — validate the token first
    token_info = verify_reset_token(token) if token else None
    return render_template("auth/reset_password.html",
                           error=None, token=token,
                           token_valid=token_info is not None,
                           token_info=token_info, success=False)


@auth_bp.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("auth.login_page"))


# -- Profile Picture Upload -----------------------------------------------

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@auth_bp.route("/profile/upload-pic", methods=["POST"])
def upload_profile_pic():
    """Upload a profile picture for the current user."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if 'profile_pic' not in request.files:
        return redirect(request.referrer or url_for("main.dashboard"))

    file = request.files['profile_pic']
    if file.filename == '':
        return redirect(request.referrer or url_for("main.dashboard"))

    if not _allowed_file(file.filename):
        return redirect(request.referrer or url_for("main.dashboard"))

    # Read file data and check size
    file_data = file.read()
    if len(file_data) > MAX_IMAGE_SIZE:
        return redirect(request.referrer or url_for("main.dashboard"))

    # Create upload directory
    upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
    os.makedirs(upload_dir, exist_ok=True)

    # Generate unique filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{user['id']}_{uuid.uuid4().hex[:8]}.{ext}"
    filepath = os.path.join(upload_dir, filename)

    # Delete old profile pic if exists
    from app.database import get_db
    db = get_db()
    old_pic = db.execute("SELECT profile_pic FROM users WHERE id = ?", (user['id'],)).fetchone()
    if old_pic and old_pic['profile_pic']:
        old_path = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles', os.path.basename(old_pic['profile_pic']))
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    # Save new file
    with open(filepath, 'wb') as f:
        f.write(file_data)

    # Update database
    pic_url = f"uploads/profiles/{filename}"
    db.execute("UPDATE users SET profile_pic = ? WHERE id = ?", (pic_url, user['id']))
    db.commit()

    # Update session
    user['profilePic'] = pic_url
    session['user'] = user

    return redirect(request.referrer or url_for("main.dashboard"))


@auth_bp.route("/profile/remove-pic", methods=["POST"])
def remove_profile_pic():
    """Remove the profile picture for the current user."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    from app.database import get_db
    db = get_db()

    # Delete file from disk
    old_pic = db.execute("SELECT profile_pic FROM users WHERE id = ?", (user['id'],)).fetchone()
    if old_pic and old_pic['profile_pic']:
        old_path = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles', os.path.basename(old_pic['profile_pic']))
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass

    # Clear from database
    db.execute("UPDATE users SET profile_pic = NULL WHERE id = ?", (user['id'],))
    db.commit()

    # Update session
    user['profilePic'] = None
    session['user'] = user

    return redirect(request.referrer or url_for("main.dashboard"))
