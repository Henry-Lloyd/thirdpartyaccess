"""Payment & Payout service — PayChangu Standard Checkout + dynamic revenue split + Mobile Money/Bank payouts."""

import uuid
import json
import math
import requests as http_requests
from datetime import datetime, timezone
from flask import current_app
from app.database import get_db
from app.modules.notifications.service import create_notification


# ═══════════════════════════════════════════════════════════════
#  REVENUE SPLIT CONFIGURATION (Dynamic — loaded from database)
# ═══════════════════════════════════════════════════════════════

DEFAULT_SPLIT_PERCENTAGE = 50.0  # Fallback if DB lookup fails


def get_current_provider_share_percentage() -> float:
    """Fetch the current provider revenue share percentage from the database.

    Returns the value stored in platform_settings table under the key
    'provider_revenue_share_percentage'. Falls back to DEFAULT_SPLIT_PERCENTAGE
    if the row is missing or the database query fails.
    """
    try:
        db = get_db()
        row = db.execute(
            "SELECT value FROM platform_settings WHERE key = 'provider_revenue_share_percentage'"
        ).fetchone()
        if row:
            return float(row["value"])
    except Exception as e:
        print(f"Warning: could not load split percentage from DB, using default. Error: {e}")
    return DEFAULT_SPLIT_PERCENTAGE


def calculate_split(total_amount: float) -> dict:
    """Calculate the revenue split for a payment.

    Dynamically fetches the provider share percentage from the database.
    Uses floor for provider_share and ceil for platform_share to handle
    odd amounts (platform gets the extra unit if not evenly divisible).
    """
    split_pct = get_current_provider_share_percentage()
    provider_share = math.floor(total_amount * split_pct / 100)
    platform_share = total_amount - provider_share  # Platform gets remainder
    return {
        "totalAmount": total_amount,
        "platformShare": platform_share,
        "providerShare": provider_share,
        "splitPercentage": split_pct,
    }


# ═══════════════════════════════════════════════════════════════
#  PAYMENT COLLECTION (Standard Checkout — seeker pays provider)
# ═══════════════════════════════════════════════════════════════

def initiate_payment(request_id: str, seeker_id: str, callback_url: str, return_url: str) -> dict:
    """Create a PayChangu hosted checkout session for an access-request fee."""
    db = get_db()

    # Fetch the access request
    req = db.execute("SELECT * FROM access_requests WHERE id = ?", (request_id,)).fetchone()
    if not req:
        raise ValueError("Access request not found")
    if req["access_fee_status"] == "paid":
        raise ValueError("Fee already paid")

    # Fetch provider details (for amount)
    provider = db.execute("SELECT * FROM providers WHERE id = ?", (req["provider_id"],)).fetchone()
    if not provider:
        raise ValueError("Provider not found")

    # Fetch seeker details
    seeker = db.execute("SELECT * FROM users WHERE id = ?", (seeker_id,)).fetchone()
    if not seeker:
        raise ValueError("Seeker not found")

    amount = int(provider["access_fee"])
    currency = "MWK"
    tx_ref = f"TPA-{uuid.uuid4().hex[:12].upper()}"

    # Pre-calculate the split
    split = calculate_split(amount)

    # Call PayChangu API
    api_url = current_app.config["PAYCHANGU_API_URL"] + "/payment"
    secret_key = current_app.config["PAYCHANGU_SECRET_KEY"]

    payload = {
        "amount": amount,
        "currency": currency,
        "email": seeker["email"],
        "first_name": seeker["first_name"],
        "last_name": seeker["last_name"],
        "callback_url": callback_url,
        "return_url": return_url,
        "tx_ref": tx_ref,
        "customization": {
            "title": "ThirdParty Access Fee",
            "description": f"Access fee for {provider['title']}"
        },
        "meta": {
            "request_id": request_id,
            "seeker_id": seeker_id,
            "provider_id": req["provider_id"],
            "platform_share": split["platformShare"],
            "provider_share": split["providerShare"],
            "split_percentage": split["splitPercentage"],
        },
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {secret_key}",
    }

    resp = http_requests.post(api_url, json=payload, headers=headers, timeout=30)
    data = resp.json()

    if resp.status_code not in (200, 201) or data.get("status") != "success":
        raise ValueError(data.get("message", "Payment initiation failed"))

    checkout_url = data["data"]["checkout_url"]

    # Store payment record with split amounts
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO payments
           (id, request_id, seeker_id, provider_id, tx_ref, paychangu_checkout_url,
            amount, currency, platform_share, provider_share, split_percentage,
            status, customer_email, customer_name, meta, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
        (payment_id, request_id, seeker_id, req["provider_id"], tx_ref, checkout_url,
         amount, currency, split["platformShare"], split["providerShare"], split["splitPercentage"],
         seeker["email"],
         f"{seeker['first_name']} {seeker['last_name']}",
         json.dumps(payload.get("meta", {})), now, now),
    )
    db.commit()

    print(f"Payment initiated: {payment_id}, tx_ref={tx_ref}, total={amount}, "
          f"platform={split['platformShare']}, provider={split['providerShare']}")
    return {
        "paymentId": payment_id,
        "txRef": tx_ref,
        "checkoutUrl": checkout_url,
        "amount": amount,
        "currency": currency,
        "split": split,
    }


def verify_payment(tx_ref: str) -> dict:
    """Verify a payment status with PayChangu and update local records including split."""
    db = get_db()
    api_url = current_app.config["PAYCHANGU_API_URL"] + f"/verify-payment/{tx_ref}"
    secret_key = current_app.config["PAYCHANGU_SECRET_KEY"]

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {secret_key}",
    }

    resp = http_requests.get(api_url, headers=headers, timeout=30)
    data = resp.json()

    payment = db.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,)).fetchone()
    if not payment:
        raise ValueError("Payment not found")

    now = datetime.now(timezone.utc).isoformat()

    if data.get("status") == "success" and data.get("data", {}).get("status") == "success":
        tx_data = data["data"]
        
        # Recalculate split based on actual paid amount (in case of discrepancy)
        actual_amount = float(tx_data.get("amount", payment["amount"]))
        split = calculate_split(actual_amount)

        db.execute(
            """UPDATE payments SET status = 'success', payment_channel = ?,
               paychangu_reference = ?, paychangu_charge_id = ?,
               amount = ?, platform_share = ?, provider_share = ?,
               updated_at = ?
               WHERE tx_ref = ?""",
            (tx_data.get("type", ""), tx_data.get("tx_ref", ""),
             tx_data.get("charge_id", ""), actual_amount,
             split["platformShare"], split["providerShare"],
             now, tx_ref),
        )

        # Also mark the access request fee as paid
        from app.modules.requests.service import update_access_fee_payment_status
        update_access_fee_payment_status(payment["request_id"], "paid")

        db.execute(
            "UPDATE access_requests SET transaction_id = ?, payment_method = ? WHERE id = ?",
            (tx_ref, tx_data.get("type", "PayChangu"), payment["request_id"]),
        )
        db.commit()

        # Notify provider about their share
        provider = db.execute("SELECT user_id, title FROM providers WHERE id = ?",
                              (payment["provider_id"],)).fetchone()
        if provider:
            create_notification(
                provider["user_id"], "payment_split", "Earnings Credited!",
                f"MWK {split['providerShare']:,.0f} has been credited to your wallet "
                f"(your {split['splitPercentage']:.0f}% share of MWK {actual_amount:,.0f} payment).",
                payment["request_id"],
            )

        print(f"Payment verified SUCCESS: {tx_ref}, total={actual_amount}, "
              f"platform={split['platformShare']}, provider={split['providerShare']}")
        return {"status": "success", "txRef": tx_ref, "split": split}
    else:
        status = data.get("data", {}).get("status", "failed")
        if status in ("failed", "cancelled"):
            db.execute("UPDATE payments SET status = ?, updated_at = ? WHERE tx_ref = ?",
                       (status, now, tx_ref))
            db.commit()
        print(f"Payment verification: {tx_ref} -> {status}")
        return {"status": status, "txRef": tx_ref}


def get_payment_by_tx_ref(tx_ref: str) -> dict | None:
    """Get a single payment by transaction reference."""
    db = get_db()
    row = db.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,)).fetchone()
    return _normalize_payment(dict(row)) if row else None


def get_payment_history(user_id: str, role: str) -> list:
    """Get payment history for a user (as seeker or provider)."""
    db = get_db()

    if role == "seeker":
        rows = db.execute(
            "SELECT * FROM payments WHERE seeker_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    else:
        provider = db.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
        if not provider:
            return []
        rows = db.execute(
            "SELECT * FROM payments WHERE provider_id = ? ORDER BY created_at DESC",
            (provider["id"],),
        ).fetchall()

    results = []
    for row in rows:
        p = _normalize_payment(dict(row))
        # Enrich with names
        seeker = db.execute("SELECT first_name, last_name FROM users WHERE id = ?", (row["seeker_id"],)).fetchone()
        prov = db.execute("SELECT title FROM providers WHERE id = ?", (row["provider_id"],)).fetchone()
        p["seekerName"] = f"{seeker['first_name']} {seeker['last_name']}" if seeker else "Unknown"
        p["providerTitle"] = prov["title"] if prov else "Unknown"
        results.append(p)

    return results


# ═══════════════════════════════════════════════════════════════
#  PLATFORM EARNINGS (Owner's share summary)
# ═══════════════════════════════════════════════════════════════

def get_platform_earnings() -> dict:
    """Get the platform owner's total earnings from revenue splits."""
    db = get_db()
    
    row = db.execute(
        "SELECT COALESCE(SUM(platform_share), 0) as total FROM payments WHERE status = 'success'"
    ).fetchone()
    total_platform = row["total"]
    
    # Total provider payouts processed (money that left platform balance)
    payout_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payouts WHERE status = 'successful'"
    ).fetchone()
    total_payouts = payout_row["total"]
    
    # Pending payouts
    pending_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payouts WHERE status IN ('pending', 'processing')"
    ).fetchone()
    pending_payouts = pending_row["total"]
    
    # Total collected = all successful payment amounts
    total_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = 'success'"
    ).fetchone()
    total_collected = total_row["total"]
    
    return {
        "totalCollected": total_collected,
        "platformShare": total_platform,
        "providerPayouts": total_payouts,
        "pendingPayouts": pending_payouts,
        "platformBalance": total_platform,  # Platform share stays in PayChangu main balance
    }


# ═══════════════════════════════════════════════════════════════
#  PROVIDER EARNINGS / BALANCE (Only their share)
# ═══════════════════════════════════════════════════════════════

def get_provider_balance(user_id: str) -> dict:
    """Calculate provider's available balance from their share minus payouts."""
    db = get_db()

    provider = db.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
    if not provider:
        return {"totalEarnings": 0, "totalWithdrawn": 0, "pendingWithdrawals": 0, "availableBalance": 0}

    provider_id = provider["id"]

    # Total provider share from successful payments
    earnings_row = db.execute(
        "SELECT COALESCE(SUM(provider_share), 0) as total FROM payments WHERE provider_id = ? AND status = 'success'",
        (provider_id,),
    ).fetchone()
    total_earnings = earnings_row["total"]

    # Total successful payouts
    withdrawn_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payouts WHERE provider_id = ? AND status = 'successful'",
        (provider_id,),
    ).fetchone()
    total_withdrawn = withdrawn_row["total"]

    # Total pending/processing payouts
    pending_row = db.execute(
        "SELECT COALESCE(SUM(amount), 0) as total FROM payouts WHERE provider_id = ? AND status IN ('pending', 'processing')",
        (provider_id,),
    ).fetchone()
    pending_withdrawals = pending_row["total"]

    available_balance = total_earnings - total_withdrawn - pending_withdrawals

    return {
        "totalEarnings": total_earnings,
        "totalWithdrawn": total_withdrawn,
        "pendingWithdrawals": pending_withdrawals,
        "availableBalance": max(0, available_balance),
    }


# ═══════════════════════════════════════════════════════════════
#  PAYOUTS (Provider withdrawals via Mobile Money / Bank)
# ═══════════════════════════════════════════════════════════════

MINIMUM_WITHDRAWAL = 1000  # MWK

# PayChangu Mobile Money Operator ref_ids
MOMO_OPERATORS = {
    "airtel_money": {
        "ref_id": "20be6c20-adeb-4b5b-a7ba-0769820df4fb",
        "name": "Airtel Money",
        "short_code": "airtel",
    },
    "tnm_mpamba": {
        "ref_id": "27494cb5-ba9e-437f-a114-4e7a7686bcca",
        "name": "TNM Mpamba",
        "short_code": "tnm",
    },
}

# PayChangu Bank UUIDs for Malawi
BANKS = {
    "national_bank": {"uuid": "82310dd1-ec9b-4fe7-a32c-2f262ef08681", "name": "National Bank of Malawi"},
    "ecobank": {"uuid": "87e62436-0553-4fb5-a76d-f27d28420c5b", "name": "Ecobank Malawi Limited"},
    "fdh_bank": {"uuid": "b064172a-8a1b-4f7f-aad7-81b036c46c57", "name": "FDH Bank Limited"},
    "standard_bank": {"uuid": "e7447c2c-c147-4907-b194-e087fe8d8585", "name": "Standard Bank Limited"},
    "centenary_bank": {"uuid": "236760c9-3045-4a01-990e-497b28d115bb", "name": "Centenary Bank"},
    "first_capital": {"uuid": "968ac588-3b1f-4d89-81ff-a3d43a599003", "name": "First Capital Limited"},
    "cdh_bank": {"uuid": "c759d7b6-ae5c-4a95-814a-79171271897a", "name": "CDH Investment Bank"},
}


def initiate_payout(user_id: str, payout_method: str, recipient_name: str,
                    recipient_account: str, amount: float,
                    bank_key: str = None) -> dict:
    """Initiate a payout/withdrawal for a provider (from their share only)."""
    db = get_db()

    # Validate provider
    provider = db.execute("SELECT * FROM providers WHERE user_id = ?", (user_id,)).fetchone()
    if not provider:
        raise ValueError("Provider profile not found")

    # Check minimum withdrawal
    if amount < MINIMUM_WITHDRAWAL:
        raise ValueError(f"Minimum withdrawal amount is MWK {MINIMUM_WITHDRAWAL:,}")

    # Check available balance (provider's share minus payouts)
    balance = get_provider_balance(user_id)
    if amount > balance["availableBalance"]:
        raise ValueError(
            f"Insufficient balance. Available: MWK {balance['availableBalance']:,.0f}, "
            f"Requested: MWK {amount:,.0f}"
        )

    # Validate payout method
    if payout_method not in ("airtel_money", "tnm_mpamba", "bank_transfer"):
        raise ValueError("Invalid payout method")

    charge_id = f"TPA-WD-{uuid.uuid4().hex[:10].upper()}"
    secret_key = current_app.config["PAYCHANGU_SECRET_KEY"]
    api_base = current_app.config["PAYCHANGU_API_URL"]

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {secret_key}",
    }

    paychangu_ref_id = None
    paychangu_trans_id = None
    paychangu_trace_id = None
    bank_uuid = None
    mobile_operator_ref_id = None
    bank_name = None
    payout_status = "pending"

    try:
        if payout_method in ("airtel_money", "tnm_mpamba"):
            # Mobile Money Payout
            operator = MOMO_OPERATORS[payout_method]
            mobile_operator_ref_id = operator["ref_id"]

            payload = {
                "mobile_money_operator_ref_id": operator["ref_id"],
                "mobile": recipient_account,
                "amount": str(int(amount)),
                "charge_id": charge_id,
                "first_name": recipient_name.split()[0] if recipient_name else "",
                "last_name": " ".join(recipient_name.split()[1:]) if len(recipient_name.split()) > 1 else "",
            }

            # For test mode, set transaction_status
            if "test" in secret_key.lower():
                payload["transaction_status"] = "successful"

            resp = http_requests.post(
                f"{api_base}/mobile-money/payouts/initialize",
                json=payload, headers=headers, timeout=30
            )
            data = resp.json()
            print(f"Mobile Money Payout Response: {json.dumps(data, indent=2)}")

            if resp.status_code in (200, 201) and data.get("status") == "success":
                payout_data = data.get("data", {})
                # API may wrap in "transaction" key
                tx = payout_data.get("transaction", payout_data)
                paychangu_ref_id = tx.get("ref_id")
                paychangu_trans_id = tx.get("trans_id")
                paychangu_trace_id = tx.get("trace_id")
                raw_status = tx.get("status", "pending").lower()
                if raw_status in ("success", "successful"):
                    payout_status = "successful"
                elif raw_status == "failed":
                    payout_status = "failed"
                elif raw_status in ("pending", "processing"):
                    payout_status = "processing"
                else:
                    payout_status = "processing"
            else:
                raise ValueError(data.get("message", "Payout initiation failed"))

        elif payout_method == "bank_transfer":
            # Bank Payout
            if not bank_key or bank_key not in BANKS:
                raise ValueError("Please select a valid bank")

            bank_info = BANKS[bank_key]
            bank_uuid = bank_info["uuid"]
            bank_name = bank_info["name"]

            payload = {
                "payout_method": "bank_transfer",
                "bank_uuid": bank_uuid,
                "amount": str(int(amount)),
                "charge_id": charge_id,
                "bank_account_name": recipient_name,
                "bank_account_number": recipient_account,
                "first_name": recipient_name.split()[0] if recipient_name else "",
                "last_name": " ".join(recipient_name.split()[1:]) if len(recipient_name.split()) > 1 else "",
            }

            resp = http_requests.post(
                f"{api_base}/direct-charge/payouts/initialize",
                json=payload, headers=headers, timeout=30
            )
            data = resp.json()
            print(f"Bank Payout Response: {json.dumps(data, indent=2)}")

            if resp.status_code in (200, 201) and data.get("status") == "success":
                payout_data = data.get("data", {})
                if isinstance(payout_data, dict):
                    tx = payout_data.get("transaction", payout_data)
                    paychangu_ref_id = tx.get("ref_id")
                    paychangu_trans_id = tx.get("trans_id")
                    paychangu_trace_id = tx.get("trace_id")
                    raw_status = tx.get("status", "pending").lower()
                    if raw_status in ("success", "successful"):
                        payout_status = "successful"
                    elif raw_status == "failed":
                        payout_status = "failed"
                    elif raw_status in ("pending", "processing"):
                        payout_status = "processing"
                    else:
                        payout_status = "processing"
            else:
                raise ValueError(data.get("message", "Bank payout initiation failed"))

    except http_requests.exceptions.RequestException as e:
        print(f"PayChangu API error: {e}")
        raise ValueError(f"Payment gateway error: {str(e)}")

    # Store payout record
    payout_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO payouts
           (id, provider_id, user_id, charge_id, payout_method, recipient_name,
            recipient_account, bank_name, bank_uuid, mobile_operator_ref_id,
            amount, currency, status, paychangu_ref_id, paychangu_trans_id,
            paychangu_trace_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'MWK', ?, ?, ?, ?, ?, ?)""",
        (payout_id, provider["id"], user_id, charge_id, payout_method, recipient_name,
         recipient_account, bank_name, bank_uuid, mobile_operator_ref_id,
         amount, payout_status, paychangu_ref_id, paychangu_trans_id,
         paychangu_trace_id, now, now),
    )
    db.commit()

    # Notify provider
    method_display = {
        "airtel_money": "Airtel Money",
        "tnm_mpamba": "TNM Mpamba",
        "bank_transfer": f"Bank Transfer ({bank_name})" if bank_name else "Bank Transfer",
    }
    create_notification(
        user_id, "payout_initiated", "Withdrawal Initiated",
        f"Your withdrawal of MWK {amount:,.0f} via {method_display.get(payout_method, payout_method)} is being processed.",
        None,
    )

    print(f"Payout initiated: {payout_id}, charge_id={charge_id}, status={payout_status}")
    return {
        "payoutId": payout_id,
        "chargeId": charge_id,
        "amount": amount,
        "status": payout_status,
        "method": payout_method,
    }


def verify_payout(payout_id: str) -> dict:
    """Check the status of a payout with PayChangu."""
    db = get_db()

    payout = db.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,)).fetchone()
    if not payout:
        raise ValueError("Payout not found")

    # Skip if already finalized
    if payout["status"] in ("successful", "failed", "cancelled"):
        return {"status": payout["status"], "payoutId": payout_id}

    secret_key = current_app.config["PAYCHANGU_SECRET_KEY"]
    api_base = current_app.config["PAYCHANGU_API_URL"]
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {secret_key}",
    }

    try:
        if payout["payout_method"] in ("airtel_money", "tnm_mpamba"):
            # Verify mobile money payout
            resp = http_requests.get(
                f"{api_base}/mobile-money/payments/{payout['charge_id']}/verify",
                headers=headers, timeout=30
            )
        else:
            # Verify bank payout
            resp = http_requests.get(
                f"{api_base}/direct-charge/payouts/{payout['charge_id']}/details",
                headers=headers, timeout=30
            )

        data = resp.json()
        print(f"Payout verification response: {json.dumps(data, indent=2)}")

        new_status = payout["status"]
        if data.get("status") == "success":
            payout_data = data.get("data", {})
            api_status = payout_data.get("status", "").lower()

            if api_status == "successful":
                new_status = "successful"
            elif api_status == "failed":
                new_status = "failed"
            elif api_status in ("pending", "processing"):
                new_status = "processing"

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE payouts SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, now, payout_id),
        )
        db.commit()

        # Notify on completion
        if new_status == "successful" and payout["status"] != "successful":
            create_notification(
                payout["user_id"], "payout_success", "Withdrawal Successful!",
                f"Your withdrawal of MWK {payout['amount']:,.0f} has been completed successfully.",
                None,
            )
        elif new_status == "failed" and payout["status"] != "failed":
            create_notification(
                payout["user_id"], "payout_failed", "Withdrawal Failed",
                f"Your withdrawal of MWK {payout['amount']:,.0f} has failed. The amount has been returned to your balance.",
                None,
            )

        return {"status": new_status, "payoutId": payout_id}

    except http_requests.exceptions.RequestException as e:
        print(f"Payout verification error: {e}")
        return {"status": payout["status"], "payoutId": payout_id, "error": str(e)}


def get_payout_history(user_id: str) -> list:
    """Get payout/withdrawal history for a provider."""
    db = get_db()

    provider = db.execute("SELECT id FROM providers WHERE user_id = ?", (user_id,)).fetchone()
    if not provider:
        return []

    rows = db.execute(
        "SELECT * FROM payouts WHERE provider_id = ? ORDER BY created_at DESC",
        (provider["id"],),
    ).fetchall()

    return [_normalize_payout(dict(row)) for row in rows]


def get_payout_by_id(payout_id: str) -> dict | None:
    """Get a single payout by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,)).fetchone()
    return _normalize_payout(dict(row)) if row else None


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════

def _normalize_payment(row: dict) -> dict:
    """Convert snake_case payment row to camelCase, including split fields."""
    return {
        "id": row["id"],
        "requestId": row["request_id"],
        "seekerId": row["seeker_id"],
        "providerId": row["provider_id"],
        "txRef": row["tx_ref"],
        "checkoutUrl": row["paychangu_checkout_url"],
        "amount": row["amount"],
        "currency": row["currency"],
        "platformShare": row.get("platform_share", 0),
        "providerShare": row.get("provider_share", 0),
        "splitPercentage": row.get("split_percentage", 50.0),
        "status": row["status"],
        "paymentChannel": row["payment_channel"],
        "paychanguReference": row["paychangu_reference"],
        "paychanguChargeId": row["paychangu_charge_id"],
        "customerEmail": row["customer_email"],
        "customerName": row["customer_name"],
        "meta": row["meta"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _normalize_payout(row: dict) -> dict:
    """Convert snake_case payout row to camelCase."""
    method_display = {
        "airtel_money": "Airtel Money",
        "tnm_mpamba": "TNM Mpamba",
        "bank_transfer": "Bank Transfer",
    }
    return {
        "id": row["id"],
        "providerId": row["provider_id"],
        "userId": row["user_id"],
        "chargeId": row["charge_id"],
        "payoutMethod": row["payout_method"],
        "payoutMethodDisplay": method_display.get(row["payout_method"], row["payout_method"]),
        "recipientName": row["recipient_name"],
        "recipientAccount": row["recipient_account"],
        "bankName": row["bank_name"],
        "amount": row["amount"],
        "currency": row["currency"],
        "status": row["status"],
        "paychanguRefId": row["paychangu_ref_id"],
        "paychanguTransId": row["paychangu_trans_id"],
        "failureReason": row["failure_reason"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
