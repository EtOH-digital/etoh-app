"""
EtOH backend — Phase A (P1 roadmap) tests:
  - Stripe SUBSCRIPTIONS (Pro / Business / Premium)
  - Admin API endpoints (X-Admin-Key)
  - Webhook handlers: subscription.created / .updated / .deleted, invoice.paid
  - Regression: credit-pack one-shot flow still works

Webhooks are HMAC-SHA256 signed using STRIPE_WEBHOOK_SECRET from backend/.env
(matches the value the backend loads via dotenv).
"""
from __future__ import annotations

import hmac
import hashlib
import json
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

# ---- Constants pulled from backend/.env (kept as constants for deterministic tests) ----
STRIPE_WEBHOOK_SECRET = "whsec_QVCyl4ZUwgAqGrcVGT72D887khZoLFh5"
ADMIN_KEY = "etoh_admin_b7a3e9d2f1c8a45e6b9d2f4a8c1e5b7d9f3a6c2e8b4d1f7a9c3e6b5d8f2a4c7e"
STRIPE_PRICE_PRO_MONTHLY = "price_1TiL0GL5QfIcbp2oznzxZjCT"

TEST_EMAIL = "vigneron@etoh-test.com"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "etoh_db"

# A fake but uniquely-shaped Stripe customer id used in forged webhook events
FAKE_CUSTOMER_ID = f"cus_test_etoh_{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _stripe_sign(payload: str, secret: str) -> str:
    """Build a Stripe-Signature header value: t=<ts>,v1=<sig>"""
    ts = int(time.time())
    signed = f"{ts}.{payload}".encode()
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _send_signed_webhook(base_url: str, event: dict) -> requests.Response:
    body = json.dumps(event)
    sig = _stripe_sign(body, STRIPE_WEBHOOK_SECRET)
    return requests.post(
        f"{base_url}/api/stripe/webhook",
        data=body,
        headers={"Content-Type": "application/json", "stripe-signature": sig},
        timeout=20,
    )


@pytest.fixture(scope="module")
def user_id(api_client, base_url):
    """Resolve the test user's user_id from /api/auth/login response."""
    r = api_client.post(
        f"{base_url}/api/auth/login",
        json={"email": TEST_EMAIL, "password": "WineLover2026"},
        timeout=30,
    )
    assert r.status_code == 200
    return r.json()["user"]["user_id"]


@pytest.fixture(scope="module", autouse=True)
def _baseline(user_id):
    """Snapshot user state, clear any prior subscription, run tests, then restore."""
    db = _mongo()
    pre = db.users.find_one({"user_id": user_id}, {"_id": 0, "credits": 1, "subscription": 1})
    pre_credits = int((pre or {}).get("credits") or 0)
    pre_sub = (pre or {}).get("subscription")

    # Reset for deterministic tests
    db.users.update_one({"user_id": user_id}, {"$unset": {"subscription": ""}})

    yield

    # Cleanup: remove test invoice rows, wallet_events from this run, restore baseline
    db.stripe_invoices.delete_many({"customer_id": FAKE_CUSTOMER_ID})
    db.wallet_events.delete_many({"user_id": user_id, "source": {"$in": ["subscription_renewal", "admin"]}})
    db.users.update_one({"user_id": user_id}, {"$set": {"credits": pre_credits}})
    if pre_sub is not None:
        db.users.update_one({"user_id": user_id}, {"$set": {"subscription": pre_sub}})
    else:
        db.users.update_one({"user_id": user_id}, {"$unset": {"subscription": ""}})


# ---------------------------------------------------------------------------
# 1) Subscription plans (PUBLIC) + features
# ---------------------------------------------------------------------------
class TestSubscriptionPlans:
    def test_plans_public_no_auth(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/subscription/plans", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        plans = {p["id"]: p for p in data["plans"]}
        assert set(plans.keys()) == {"free", "pro", "business", "premium"}
        # Pro plan checks
        pro = plans["pro"]
        assert pro["price_eur"] == 19
        assert pro["credits_monthly"] == 300
        assert isinstance(pro["feature_lines"], list) and len(pro["feature_lines"]) >= 3
        assert pro["stripe_configured"] is True
        # Business + Premium configured
        assert plans["business"]["stripe_configured"] is True
        assert plans["premium"]["stripe_configured"] is True
        # Free always considered "configured"
        assert plans["free"]["stripe_configured"] is True

    def test_subscription_me_default_free(self, api_client, base_url, auth_headers):
        r = api_client.get(f"{base_url}/api/subscription/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["plan_id"] == "free"
        assert body["credits_monthly"] == 20
        assert body["status"] in (None, "inactive", "")
        assert isinstance(body["features"], dict)
        assert body["features"]["rag"] is False
        assert body["features"]["hub_chat_public"] is False

    def test_features_me(self, api_client, base_url, auth_headers):
        r = api_client.get(f"{base_url}/api/features/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["plan_id"] == "free"
        assert body["features"]["rag"] is False
        assert body["features"]["hub_chat_public"] is False


# ---------------------------------------------------------------------------
# 2) Checkout & portal (order matters: portal BEFORE checkout)
# ---------------------------------------------------------------------------
class TestSubscriptionCheckout:
    def test_portal_without_customer_returns_400(self, api_client, base_url, auth_headers, user_id):
        # Ensure no stripe_customer_id is set
        _mongo().users.update_one({"user_id": user_id}, {"$unset": {"subscription": ""}})
        r = api_client.post(f"{base_url}/api/subscription/portal", headers=auth_headers, timeout=15)
        assert r.status_code == 400, r.text
        assert "subscribe first" in r.json().get("detail", "").lower()

    def test_checkout_free_plan_returns_400(self, api_client, base_url, auth_headers):
        r = api_client.post(
            f"{base_url}/api/subscription/checkout",
            headers=auth_headers,
            json={"plan_id": "free", "success_url": "https://app.etoh.io/ok", "cancel_url": "https://app.etoh.io/cancel"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "free plan" in r.json()["detail"].lower()

    def test_checkout_unknown_plan_returns_400(self, api_client, base_url, auth_headers):
        r = api_client.post(
            f"{base_url}/api/subscription/checkout",
            headers=auth_headers,
            json={"plan_id": "unknown", "success_url": "https://x/y", "cancel_url": "https://x/z"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_checkout_pro_returns_stripe_subscription_url(self, api_client, base_url, auth_headers, user_id):
        r = api_client.post(
            f"{base_url}/api/subscription/checkout",
            headers=auth_headers,
            json={"plan_id": "pro", "success_url": "https://app.etoh.io/ok", "cancel_url": "https://app.etoh.io/cancel"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "checkout_url" in body and body["checkout_url"].startswith("https://checkout.stripe.com/")
        assert "cs_test_" in body["checkout_url"] or "cs_test_" in body.get("session_id", "")
        # Customer must have been lazily created and persisted
        user = _mongo().users.find_one({"user_id": user_id}, {"_id": 0, "subscription": 1})
        cid = (user.get("subscription") or {}).get("stripe_customer_id")
        assert cid and cid.startswith("cus_"), f"stripe_customer_id not persisted: {user}"


# ---------------------------------------------------------------------------
# 3) Subscription webhooks (sub created → invoice paid x2 → deleted)
# ---------------------------------------------------------------------------
class TestSubscriptionWebhooks:
    def test_subscription_created_upserts_user(self, api_client, base_url, auth_headers, user_id):
        # Pre-link the user to the FAKE customer id so the webhook flow is deterministic
        _mongo().users.update_one(
            {"user_id": user_id},
            {"$set": {"subscription.stripe_customer_id": FAKE_CUSTOMER_ID}},
        )
        event_id = f"evt_test_sub_create_{uuid.uuid4().hex[:8]}"
        event = {
            "id": event_id,
            "object": "event",
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": f"sub_test_{uuid.uuid4().hex[:8]}",
                    "object": "subscription",
                    "customer": FAKE_CUSTOMER_ID,
                    "status": "active",
                    "current_period_end": int(time.time()) + 30 * 24 * 3600,
                    "cancel_at_period_end": False,
                    "items": {"data": [{"price": {"id": STRIPE_PRICE_PRO_MONTHLY}}]},
                    "metadata": {"app_user_id": user_id, "plan_id": "pro"},
                }
            },
        }
        r = _send_signed_webhook(base_url, event)
        assert r.status_code == 200, r.text
        # /subscription/me must now reflect Pro / active
        me = api_client.get(f"{base_url}/api/subscription/me", headers=auth_headers, timeout=15).json()
        assert me["plan_id"] == "pro", me
        assert me["status"] == "active", me

    def test_invoice_paid_credits_monthly_amount(self, api_client, base_url, auth_headers, user_id):
        db = _mongo()
        # Snapshot credits
        before = int(db.users.find_one({"user_id": user_id})["credits"])
        invoice_id = f"in_test_{uuid.uuid4().hex[:8]}"
        event_id_1 = f"evt_test_inv_1_{uuid.uuid4().hex[:8]}"
        invoice_obj = {
            "id": invoice_id,
            "object": "invoice",
            "customer": FAKE_CUSTOMER_ID,
            "billing_reason": "subscription_cycle",
            "amount_paid": 1900,
            "currency": "eur",
        }
        event_v1 = {
            "id": event_id_1,
            "object": "event",
            "type": "invoice.paid",
            "data": {"object": invoice_obj},
        }
        r1 = _send_signed_webhook(base_url, event_v1)
        assert r1.status_code == 200, r1.text
        after = int(db.users.find_one({"user_id": user_id})["credits"])
        assert after - before == 300, f"Expected +300 credits (Pro monthly), got {after - before}"
        # wallet_events row created
        evt = db.wallet_events.find_one({"stripe_invoice_id": invoice_id})
        assert evt is not None and evt["credits"] == 300 and evt["source"] == "subscription_renewal"

        # Replay same invoice via a NEW Stripe event id → still must be idempotent on invoice_id
        event_id_2 = f"evt_test_inv_2_{uuid.uuid4().hex[:8]}"
        event_v2 = {**event_v1, "id": event_id_2}
        r2 = _send_signed_webhook(base_url, event_v2)
        assert r2.status_code == 200, r2.text
        after2 = int(db.users.find_one({"user_id": user_id})["credits"])
        assert after2 == after, f"Replay should NOT re-credit, got {after2 - after} extra credits"

    def test_subscription_deleted_downgrades_to_free(self, api_client, base_url, auth_headers, user_id):
        event_id = f"evt_test_sub_del_{uuid.uuid4().hex[:8]}"
        event = {
            "id": event_id,
            "object": "event",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": f"sub_test_{uuid.uuid4().hex[:8]}",
                    "object": "subscription",
                    "customer": FAKE_CUSTOMER_ID,
                    "status": "canceled",
                    "items": {"data": [{"price": {"id": STRIPE_PRICE_PRO_MONTHLY}}]},
                }
            },
        }
        r = _send_signed_webhook(base_url, event)
        assert r.status_code == 200, r.text
        me = api_client.get(f"{base_url}/api/subscription/me", headers=auth_headers, timeout=15).json()
        assert me["status"] == "canceled", me
        assert me["plan_id"] == "free", me


# ---------------------------------------------------------------------------
# 4) Admin endpoints (X-Admin-Key)
# ---------------------------------------------------------------------------
class TestAdminAPI:
    def test_admin_health_missing_key(self, base_url):
        r = requests.get(f"{base_url}/api/admin/health", timeout=10)
        assert r.status_code == 401
        assert "missing" in r.json().get("detail", "").lower()

    def test_admin_health_wrong_key(self, base_url):
        r = requests.get(
            f"{base_url}/api/admin/health",
            headers={"X-Admin-Key": "totally_wrong_key_12345"},
            timeout=10,
        )
        assert r.status_code == 403
        assert "invalid" in r.json().get("detail", "").lower()

    def test_admin_health_valid_key(self, base_url):
        r = requests.get(
            f"{base_url}/api/admin/health",
            headers={"X-Admin-Key": ADMIN_KEY},
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True

    def test_admin_metrics_summary(self, base_url):
        r = requests.get(
            f"{base_url}/api/admin/metrics/summary",
            headers={"X-Admin-Key": ADMIN_KEY},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k in (
            "users_count", "active_subscriptions", "subscriptions_by_plan",
            "mrr_eur", "arr_eur", "signups_30d",
            "hub_items", "hub_public_views", "llm_events_30d", "generated_at",
        ):
            assert k in body, f"missing field: {k}"
        assert isinstance(body["subscriptions_by_plan"], dict)
        assert isinstance(body["users_count"], int)
        assert isinstance(body["mrr_eur"], (int, float))
        assert isinstance(body["arr_eur"], (int, float))

    def test_admin_grant_credits_delta_zero_rejected(self, base_url, user_id):
        r = requests.post(
            f"{base_url}/api/admin/users/{user_id}/credits",
            headers={"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"},
            json={"delta": 0, "reason": "test"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_admin_grant_credits_unknown_user(self, base_url):
        r = requests.post(
            f"{base_url}/api/admin/users/UNKNOWN_USER_XYZ/credits",
            headers={"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"},
            json={"delta": 50, "reason": "test"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_admin_grant_credits_happy_path(self, base_url, user_id):
        db = _mongo()
        before = int(db.users.find_one({"user_id": user_id})["credits"])
        r = requests.post(
            f"{base_url}/api/admin/users/{user_id}/credits",
            headers={"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"},
            json={"delta": 50, "reason": "test"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        after = int(db.users.find_one({"user_id": user_id})["credits"])
        assert after - before == 50
        evt = db.wallet_events.find_one(
            {"user_id": user_id, "source": "admin", "reason": "test"},
            sort=[("created_at", -1)],
        )
        assert evt is not None and evt["credits"] == 50


# ---------------------------------------------------------------------------
# 5) Regression: existing credit-pack flow + previously tested endpoints
# ---------------------------------------------------------------------------
class TestRegression:
    def test_wallet_packs_listing(self, api_client, base_url, auth_headers):
        r = api_client.get(f"{base_url}/api/wallet/packs", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        packs = r.json().get("packs") or r.json()
        assert isinstance(packs, list) and len(packs) >= 3

    def test_wallet_checkout_credit_pack_starter(self, api_client, base_url, auth_headers):
        r = api_client.post(
            f"{base_url}/api/wallet/checkout",
            headers=auth_headers,
            json={
                "pack_id": "starter",
                "success_url": "https://app.etoh.io/ok",
                "cancel_url": "https://app.etoh.io/cancel",
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # The credit pack flow must remain mode=payment — i.e. NOT a subscription URL
        url = body.get("checkout_url") or body.get("url")
        assert url and url.startswith("https://checkout.stripe.com/"), body

    def test_credit_pack_webhook_still_credits(self, api_client, base_url, auth_headers, user_id):
        """Existing checkout.session.completed for a starter pack still adds +100 credits."""
        db = _mongo()
        before = int(db.users.find_one({"user_id": user_id})["credits"])
        event_id = f"evt_test_pack_{uuid.uuid4().hex[:8]}"
        session_id = f"cs_test_pack_{uuid.uuid4().hex[:8]}"
        event = {
            "id": event_id,
            "object": "event",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "metadata": {"user_id": user_id, "pack_id": "starter"},
                    "mode": "payment",
                }
            },
        }
        r = _send_signed_webhook(base_url, event)
        assert r.status_code == 200, r.text
        after = int(db.users.find_one({"user_id": user_id})["credits"])
        assert after - before == 100, f"Expected +100 from starter pack, got {after - before}"
        # Cleanup
        db.wallet_events.delete_many({"stripe_session_id": session_id})

    def test_existing_endpoints_smoke(self, api_client, base_url, auth_headers):
        for path in ("/api/", "/api/auth/me", "/api/hub/me", "/api/crm/contacts", "/api/dashboard/metrics", "/api/wallet/packs"):
            r = api_client.get(f"{base_url}{path}", headers=auth_headers, timeout=15)
            assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
