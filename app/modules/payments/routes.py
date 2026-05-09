"""Payment & Payout routes — API + page routes for PayChangu integration."""

import json
import hashlib
import hmac
from flask import (
    Blueprint, request, jsonify, render_template,
    redirect, url_for, session, flash, current_app,
)

from app.modules.payments.service import (
    initiate_payment, verify_payment, get_payment_by_tx_ref, get_payment_history,
    get_provider_balance, get_platform_earnings, initiate_payout, verify_payout,
    get_payout_history, get_payout_by_id, MINIMUM_WITHDRAWAL, MOMO_OPERATORS, BANKS,
    get_current_provider_share_percentage,
)

payments_bp = Blueprint("payments", __name__)


# ═══════════════════════════════════════════════════════════════
#  PAYMENT COLLECTION ROUTES (Seeker pays)
# ═══════════════════════════════════════════════════════════════

@payments_bp.route("/payments/initiate/<request_id>", methods=["POST"])
def initiate_payment_page(request_id):
    """Initiate PayChangu payment and redirect to checkout."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    try:
        base_url = current_app.config.get("BASE_URL") or request.host_url.rstrip("/")
        callback_url = f"{base_url}/payments/callback"
        return_url = f"{base_url}/payments/cancelled/{request_id}"

        result = initiate_payment(request_id, user["id"], callback_url, return_url)
        return redirect(result["checkoutUrl"])
    except ValueError as e:
        return render_template("payments/payment_error.html", user=user, error=str(e))
    except Exception as e:
        return render_template("payments/payment_error.html", user=user,
                               error=f"An unexpected error occurred: {str(e)}")


@payments_bp.route("/payments/callback")
def payment_callback():
    """PayChangu redirects here after payment — verify and show status."""
    user = session.get("user")
    tx_ref = request.args.get("tx_ref")

    if not tx_ref:
        if user:
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.login_page"))

    try:
        result = verify_payment(tx_ref)
        payment = get_payment_by_tx_ref(tx_ref)
        # Load dynamic split for display
        pct = get_current_provider_share_percentage()
        split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}
        return render_template("payments/payment_status.html",
                               user=user, payment=payment, verification=result, split=split)
    except Exception as e:
        return render_template("payments/payment_error.html",
                               user=user, error=str(e))


@payments_bp.route("/payments/cancelled/<request_id>")
def payment_cancelled(request_id):
    """Shown when a user cancels a PayChangu payment."""
    user = session.get("user")
    return render_template("payments/payment_cancelled.html",
                           user=user, request_id=request_id)


@payments_bp.route("/payments/webhook", methods=["POST"])
def payment_webhook():
    """Handle PayChangu webhook notifications."""
    webhook_secret = current_app.config.get("PAYCHANGU_WEBHOOK_SECRET", "")

    if webhook_secret:
        signature = request.headers.get("Signature", "")
        payload_bytes = request.get_data()
        expected = hmac.new(
            webhook_secret.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return jsonify({"error": "Invalid signature"}), 403

    try:
        data = request.get_json(silent=True) or {}
        tx_ref = data.get("tx_ref") or data.get("data", {}).get("tx_ref")
        if tx_ref:
            verify_payment(tx_ref)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"status": "ok"}), 200


# ── Payment History Page ──────────────────────────────────────

@payments_bp.route("/payments/history")
def payment_history_page():
    """Show payment history for the logged-in user."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    payments = get_payment_history(user["id"], user["role"])
    # Load dynamic split for column header
    pct = get_current_provider_share_percentage()
    split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}
    return render_template("payments/payment_history.html", user=user, payments=payments, split=split)


# ═══════════════════════════════════════════════════════════════
#  PAYOUT / WITHDRAWAL ROUTES (Provider withdraws earnings)
# ═══════════════════════════════════════════════════════════════

@payments_bp.route("/wallet")
def wallet_page():
    """Provider wallet — show balance and withdrawal options."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if user["role"] != "provider":
        return redirect(url_for("main.dashboard"))

    balance = get_provider_balance(user["id"])
    payouts = get_payout_history(user["id"])
    recent_payouts = payouts[:5]  # Show last 5

    # Load dynamic split for display
    pct = get_current_provider_share_percentage()
    split = {"providerPercentage": pct, "platformPercentage": 100.0 - pct}

    return render_template("payments/wallet.html",
                           user=user, balance=balance,
                           recent_payouts=recent_payouts,
                           min_withdrawal=MINIMUM_WITHDRAWAL,
                           banks=BANKS, split=split)


@payments_bp.route("/wallet/withdraw", methods=["GET", "POST"])
def withdraw_page():
    """Withdrawal form and processing."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if user["role"] != "provider":
        return redirect(url_for("main.dashboard"))

    balance = get_provider_balance(user["id"])
    error = None
    success = None

    if request.method == "POST":
        payout_method = request.form.get("payout_method", "")
        recipient_name = request.form.get("recipient_name", "").strip()
        recipient_account = request.form.get("recipient_account", "").strip()
        amount_str = request.form.get("amount", "0").strip()
        bank_key = request.form.get("bank_key", "")

        try:
            amount = float(amount_str)
        except ValueError:
            error = "Please enter a valid amount"
            return render_template("payments/withdraw.html",
                                   user=user, balance=balance, error=error,
                                   min_withdrawal=MINIMUM_WITHDRAWAL, banks=BANKS)

        try:
            result = initiate_payout(
                user_id=user["id"],
                payout_method=payout_method,
                recipient_name=recipient_name,
                recipient_account=recipient_account,
                amount=amount,
                bank_key=bank_key if payout_method == "bank_transfer" else None,
            )
            # Refresh balance
            balance = get_provider_balance(user["id"])
            return render_template("payments/withdraw_success.html",
                                   user=user, result=result, balance=balance)
        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"An unexpected error occurred: {str(e)}"

    return render_template("payments/withdraw.html",
                           user=user, balance=balance, error=error,
                           min_withdrawal=MINIMUM_WITHDRAWAL, banks=BANKS)


@payments_bp.route("/wallet/payouts")
def payout_history_page():
    """Full payout/withdrawal history."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    if user["role"] != "provider":
        return redirect(url_for("main.dashboard"))

    payouts = get_payout_history(user["id"])
    balance = get_provider_balance(user["id"])

    return render_template("payments/payout_history.html",
                           user=user, payouts=payouts, balance=balance)


@payments_bp.route("/wallet/payout/<payout_id>")
def payout_detail_page(payout_id):
    """Single payout detail with verification."""
    user = session.get("user")
    if not user:
        return redirect(url_for("auth.login_page"))

    # Try to verify/refresh status
    try:
        verify_payout(payout_id)
    except Exception:
        pass

    payout = get_payout_by_id(payout_id)
    if not payout:
        return render_template("payments/payment_error.html", user=user,
                               error="Payout not found")

    return render_template("payments/payout_detail.html", user=user, payout=payout)


# ── API Endpoints ──────────────────────────────────────────────

@payments_bp.route("/api/wallet/balance")
def api_get_balance():
    """API: Get provider balance."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    balance = get_provider_balance(user["id"])
    return jsonify(balance)


@payments_bp.route("/api/wallet/payouts")
def api_get_payouts():
    """API: Get payout history."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    payouts = get_payout_history(user["id"])
    return jsonify(payouts)


@payments_bp.route("/api/wallet/payout/<payout_id>/verify", methods=["POST"])
def api_verify_payout(payout_id):
    """API: Verify a payout status."""
    try:
        result = verify_payout(payout_id)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@payments_bp.route("/api/split-info")
def api_split_info():
    """API: Get the current revenue split configuration."""
    pct = get_current_provider_share_percentage()
    platform_pct = 100 - pct
    return jsonify({
        "splitPercentage": pct,
        "providerPercentage": pct,
        "platformPercentage": platform_pct,
        "description": f"Revenue is split {platform_pct:.0f}/{pct:.0f} between platform and provider.",
    })


@payments_bp.route("/api/platform/earnings")
def api_platform_earnings():
    """API: Get platform owner's earnings summary (admin only)."""
    user = session.get("user")
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    earnings = get_platform_earnings()
    return jsonify(earnings)
