"""
Phase C+D — Public Hub conversational chat + lead capture + EAN enrichment.

Tests cover (per review_request):
  - /api/public/hub/{slug}            (chat_enabled, views tracking)
  - /api/public/hub/{slug}/chat       (LLM reply, session persistence, rate limit, plan gate)
  - /api/public/hub/{slug}/lead       (prospect creation, RGPD consent, session linkage)
  - /api/enrich/ean/{ean}             (OpenFoodFacts pass-through, validation, auth)
  - Regression                        (/api/, /api/auth/me, /api/subscription/plans,
                                       /api/admin/health, /api/wallet/packs, /api/hub/me)

The test user (vigneron@etoh-test.com) is promoted to Pro via direct Mongo write
before chat tests, and reverted to free at teardown. Created prospects and the
hub_chat_session are cleaned up too.
"""

import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

from conftest import BASE_URL  # type: ignore

TEST_EMAIL = "vigneron@etoh-test.com"
HUB_SLUG = "domaine-test"
LEAD_EMAIL = "leadtest@example.com"
ADMIN_KEY = "etoh_admin_b7a3e9d2f1c8a45e6b9d2f4a8c1e5b7d9f3a6c2e8b4d1f7a9c3e6b5d8f2a4c7e"

mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
db = mongo[os.environ.get("DB_NAME", "etoh_db")]


def _set_plan(plan_id: str, status: str = "active"):
    if plan_id == "free":
        db.users.update_one(
            {"email": TEST_EMAIL},
            {"$set": {"subscription.plan_id": "free", "subscription.status": "inactive"}},
        )
    else:
        db.users.update_one(
            {"email": TEST_EMAIL},
            {"$set": {
                "subscription.plan_id": plan_id,
                "subscription.status": status,
                "subscription.stripe_customer_id": "cus_test_local",
            }},
        )


@pytest.fixture(scope="module", autouse=True)
def promote_to_pro_and_cleanup():
    """Snapshot user state, promote to Pro for the chat tests, then revert + clean."""
    snap = db.users.find_one({"email": TEST_EMAIL}, {"subscription": 1})
    original_sub = (snap or {}).get("subscription")
    _set_plan("pro")

    yield

    # Revert plan
    if original_sub is None:
        db.users.update_one({"email": TEST_EMAIL}, {"$unset": {"subscription": ""}})
    else:
        db.users.update_one({"email": TEST_EMAIL}, {"$set": {"subscription": original_sub}})

    # Cleanup prospects and chat sessions created during tests
    db.prospects.delete_many({"email": LEAD_EMAIL})
    db.hub_chat_sessions.delete_many({"slug": HUB_SLUG, "lead_email": LEAD_EMAIL})
    # Best-effort: remove any other sessions touched by the rate-limit test (use very fresh ones)
    db.hub_chat_sessions.delete_many({"slug": HUB_SLUG, "messages.content": {"$regex": "^Bonjour"}})


# ---------------------------------------------------------------------------
# Public Hub GET — chat_enabled + view tracking
# ---------------------------------------------------------------------------
class TestPublicHubGet:
    def test_hub_returns_chat_enabled_when_pro(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/public/hub/{HUB_SLUG}", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("slug") == HUB_SLUG
        assert body.get("chat_enabled") is True
        assert "company" in body and isinstance(body["items"], list)

    def test_hub_views_increment(self, api_client):
        before = db.hub_views.find_one({"slug": HUB_SLUG}) or {"views": 0}
        baseline = int(before.get("views") or 0)
        for _ in range(3):
            r = api_client.get(f"{BASE_URL}/api/public/hub/{HUB_SLUG}", timeout=20)
            assert r.status_code == 200
        after = db.hub_views.find_one({"slug": HUB_SLUG}) or {"views": 0}
        assert int(after.get("views") or 0) >= baseline + 3

    def test_hub_invalid_slug_returns_404_chat(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/public/hub/INVALID_SLUG_xyz/chat",
            json={"message": "hi"},
            timeout=20,
        )
        assert r.status_code == 404
        assert "hub not found" in r.text.lower()


# ---------------------------------------------------------------------------
# Public Hub chat — happy path (uses real LLM, keep msgs short)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def chat_session(api_client):
    """First chat turn — returns the session_id used by lead capture tests."""
    r = api_client.post(
        f"{BASE_URL}/api/public/hub/{HUB_SLUG}/chat",
        json={"message": "Bonjour, vos vins ?"},
        timeout=60,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    data = r.json()
    assert isinstance(data.get("session_id"), str) and data["session_id"].startswith("hubchat_")
    assert isinstance(data.get("reply"), str) and len(data["reply"]) > 5
    assert data.get("language") == "fr"
    assert data.get("user_message_count") == 1
    return data["session_id"]


class TestPublicHubChat:
    def test_chat_first_message(self, chat_session):
        # Fixture-driven; just ensure id reaches second test
        assert chat_session.startswith("hubchat_")

    def test_chat_session_persisted_in_mongo(self, chat_session):
        sess = db.hub_chat_sessions.find_one({"session_id": chat_session})
        assert sess is not None
        assert sess.get("slug") == HUB_SLUG
        assert sess.get("language") == "fr"
        assert isinstance(sess.get("messages"), list) and len(sess["messages"]) >= 2

    def test_chat_second_message_increments_count(self, api_client, chat_session):
        r = api_client.post(
            f"{BASE_URL}/api/public/hub/{HUB_SLUG}/chat",
            json={"session_id": chat_session, "message": "Prix moyen ?"},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["session_id"] == chat_session
        assert data["user_message_count"] == 2
        assert isinstance(data["reply"], str) and len(data["reply"]) > 5


# ---------------------------------------------------------------------------
# Lead capture — requires the chat session created above (re-promote to Pro
# was kept by the autouse fixture; we just need a fresh session).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def lead_session(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/public/hub/{HUB_SLUG}/chat",
        json={"message": "Salut !"},
        timeout=60,
    )
    assert r.status_code == 200, f"chat for lead session failed: {r.status_code} {r.text}"
    return r.json()["session_id"]


class TestLeadCapture:
    def test_lead_without_consent_400(self, api_client, lead_session):
        r = api_client.post(
            f"{BASE_URL}/api/public/hub/{HUB_SLUG}/lead",
            json={"session_id": lead_session, "email": LEAD_EMAIL, "name": "Jane", "consent": False},
            timeout=20,
        )
        assert r.status_code == 400
        assert "consent" in r.text.lower()

    def test_lead_with_consent_creates_prospect(self, api_client, lead_session):
        r = api_client.post(
            f"{BASE_URL}/api/public/hub/{HUB_SLUG}/lead",
            json={
                "session_id": lead_session,
                "email": LEAD_EMAIL,
                "name": "John Doe",
                "consent": True,
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        pid = body.get("prospect_id")
        assert isinstance(pid, str) and pid.startswith("pr_")

        # Verify prospect persistence
        pros = db.prospects.find_one({"id": pid})
        assert pros is not None
        assert pros.get("source") == "hub_public_chat"
        assert pros.get("hub_slug") == HUB_SLUG
        assert pros.get("email") == LEAD_EMAIL
        assert "Transcript:" in (pros.get("notes") or "")

        # Verify session got updated
        sess = db.hub_chat_sessions.find_one({"session_id": lead_session})
        assert sess and sess.get("lead_captured") is True
        assert sess.get("prospect_id") == pid


# ---------------------------------------------------------------------------
# Feature gate: revert to free → 402
# ---------------------------------------------------------------------------
class TestFeatureGate:
    def test_free_plan_blocks_chat(self, api_client):
        _set_plan("free")
        try:
            r = api_client.post(
                f"{BASE_URL}/api/public/hub/{HUB_SLUG}/chat",
                json={"message": "hello"},
                timeout=20,
            )
            assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text}"
            assert "paid" in r.text.lower() or "plan" in r.text.lower()

            # And /api/public/hub/{slug} should report chat_enabled=false
            r2 = api_client.get(f"{BASE_URL}/api/public/hub/{HUB_SLUG}", timeout=20)
            assert r2.status_code == 200
            assert r2.json().get("chat_enabled") is False
        finally:
            # Re-promote so the module finishes in a consistent state for other tests
            _set_plan("pro")


# ---------------------------------------------------------------------------
# EAN enrichment (Phase D)
# ---------------------------------------------------------------------------
class TestEanEnrichment:
    def test_ean_valid_nutella(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/enrich/ean/3017620422003", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("found") is True
        assert body.get("ean") == "3017620422003"
        name = (body.get("name") or "").lower()
        brand = (body.get("brand") or "").lower()
        assert "nutella" in name or "nutella" in brand
        # OpenFoodFacts may return brand as "Nutella, Yum yum" or include Ferrero — accept either
        assert any(b in (name + " " + brand) for b in ("nutella", "ferrero"))
        img = body.get("image_url") or ""
        assert isinstance(img, str) and (img.startswith("http://") or img.startswith("https://"))

    def test_ean_too_short_400(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/enrich/ean/12", headers=auth_headers, timeout=15)
        assert r.status_code == 400
        assert "8-14 digits" in r.text or "8" in r.text

    def test_ean_not_found_404(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/enrich/ean/0000000000000", headers=auth_headers, timeout=20)
        assert r.status_code == 404
        assert "not found" in r.text.lower()

    def test_ean_requires_auth(self, api_client):
        # Use a *fresh* requests session without auth headers
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/enrich/ean/3017620422003", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# ---------------------------------------------------------------------------
# Regression — make sure prior endpoints still respond 200
# ---------------------------------------------------------------------------
class TestRegression:
    def test_root(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/", timeout=15)
        assert r.status_code == 200

    def test_auth_me(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("email") == TEST_EMAIL

    def test_subscription_plans_public(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/subscription/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json().get("plans") or []
        assert any(p.get("id") == "pro" for p in plans)

    def test_admin_health_with_key(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/admin/health",
            headers={"X-Admin-Key": ADMIN_KEY},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_wallet_packs(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/wallet/packs", headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_hub_me(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/hub/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Rate limiting (10/minute per IP) — placed LAST so prior chat tests don't
# trip the limit. Every prior /chat POST counts toward the same IP bucket —
# we expect >=1 429 within 12 rapid calls. Uses a fresh hub slug to start
# the per-IP bucket clean.
# ---------------------------------------------------------------------------
class TestZZRateLimit:
    def test_chat_rate_limit_429(self, api_client):
        # Use the real hub slug so we hit the (post-404) rate-limit path
        statuses = []
        for _ in range(14):
            r = api_client.post(
                f"{BASE_URL}/api/public/hub/{HUB_SLUG}/chat",
                json={"message": "x"},
                timeout=30,
            )
            statuses.append(r.status_code)
            if r.status_code == 429:
                break
            time.sleep(0.05)
        assert 429 in statuses, f"No 429 observed in {statuses}"

