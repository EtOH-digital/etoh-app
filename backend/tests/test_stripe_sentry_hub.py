"""Iteration 3: Sentry + Stripe webhook (idempotent) + Hub/CRM/Wallet checkout + rate limit + profile auto-extract.

Covers the P0 production blockers per the review request:
  - Sentry middleware doesn't break existing endpoints
  - /api/debug/sentry returns 500 (capture path)
  - Stripe webhook (alias /api/stripe/webhook == /api/wallet/webhook)
      * No sig         → 400
      * Forged sig     → 400
      * Valid sig      → 200 received:true, credits ++
      * Replay         → 200 received:true, duplicate:true (no double credit)
  - Wallet packs + checkout (Stripe TEST → cs_test_)
  - Hub CRUD + public hub (no auth) + hub extract (FR text → product)
  - CRM contacts list
  - Coach rate limit (llm_rate_limit(30)) → 429 after ~30 hits/min
  - Profile auto-extract (FR sentence → target_countries learned)
"""
import os
import time
import json
import hmac
import hashlib
import uuid
import re
import requests
import pytest
import stripe
from pymongo import MongoClient

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"
STRIPE_WEBHOOK_SECRET = "whsec_QVCyl4ZUwgAqGrcVGT72D887khZoLFh5"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "etoh_db")


# ---------- Helpers ----------
def _login(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
        timeout=30,
    )
    if r.status_code != 200:
        # try signup once if seed missing
        api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json={
                "email": "vigneron@etoh-test.com",
                "password": "WineLover2026",
                "name": "Jean Dupont",
            },
            timeout=30,
        )
        r = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
            timeout=30,
        )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(api_client):
    return _login(api_client)


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_id(api_client, auth_headers):
    r = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


# ---------- Health ----------
class TestHealth:
    def test_root(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "EtOH API"
        assert body["status"] == "ok"


# ---------- Sentry capture path ----------
class TestSentry:
    def test_debug_sentry_returns_500(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/debug/sentry", timeout=15)
        # Endpoint intentionally raises to exercise Sentry capture middleware
        assert r.status_code == 500, r.text


# ---------- Auth ----------
class TestAuth:
    def test_signup_new(self, api_client):
        email = f"TEST_signup_{uuid.uuid4().hex[:8]}@etoh-test.com"
        r = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json={"email": email, "password": "TestPass2026", "name": "TEST"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert body["user"]["email"].lower() == email.lower()
        assert "_id" not in body["user"]

    def test_login_seeded(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body

    def test_me(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        u = r.json()
        assert u["email"] == "vigneron@etoh-test.com"
        assert "credits" in u
        assert "business_profile" in u
        assert "_id" not in u


# ---------- Coach (short FR prompt) ----------
class TestCoach:
    def test_message(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/coach/message",
            json={"message": "Bonjour", "language": "fr"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "reply" in body
        assert len(body["reply"]) > 10
        assert "session_id" in body


# ---------- Studio ----------
class TestStudio:
    def test_linkedin_post(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/studio/generate",
            json={
                "template": "linkedin_post",
                "brief": "Annonce du nouveau millésime 2024",
                "language": "fr",
            },
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["template"] == "linkedin_post"
        assert len(body["content"]) > 50


# ---------- Pilot v2 search + draft ----------
class TestPilotV2:
    SEARCH = {}

    def test_search_returns_targets(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/pilot/search",
            json={"query": "cavistes Lyon vins bio", "language": "fr"},
            headers=auth_headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        targets = body.get("targets", [])
        assert len(targets) >= 4, f"Expected >=4 targets, got {len(targets)}"
        TestPilotV2.SEARCH["id"] = body["search_id"]
        TestPilotV2.SEARCH["targets"] = targets

    def test_draft_email_for_first_target(self, api_client, auth_headers):
        sid = TestPilotV2.SEARCH.get("id")
        if not sid:
            pytest.skip("No search id from previous test")
        tid = TestPilotV2.SEARCH["targets"][0]["id"]
        r = api_client.post(
            f"{BASE_URL}/api/pilot/draft",
            json={"search_id": sid, "target_id": tid, "channel": "email", "language": "fr"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channel"] == "email"
        assert body.get("subject"), "Email draft missing subject"
        assert len(body.get("body") or "") > 30


# ---------- Hub ----------
class TestHub:
    SLUG = None
    ITEM_ID = None

    def test_hub_me(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/hub/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "slug" in body and body["slug"]
        assert "company" in body
        assert "items" in body and isinstance(body["items"], list)
        TestHub.SLUG = body["slug"]

    def test_hub_item_crud(self, api_client, auth_headers):
        # Create
        payload = {
            "type": "product",
            "name": "TEST_Vin Rouge Bordeaux 2022",
            "category": "wine",
            "price": 19.5,
            "currency": "EUR",
            "description": "Test wine for CRUD",
        }
        r = api_client.post(
            f"{BASE_URL}/api/hub/items", json=payload, headers=auth_headers, timeout=20
        )
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["name"] == payload["name"]
        assert item["price"] == 19.5
        assert "id" in item
        assert "_id" not in item
        TestHub.ITEM_ID = item["id"]

        # Patch
        r = api_client.patch(
            f"{BASE_URL}/api/hub/items/{TestHub.ITEM_ID}",
            json={"price": 22.0, "description": "Updated"},
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["price"] == 22.0
        assert updated["description"] == "Updated"

        # Delete
        r = api_client.delete(
            f"{BASE_URL}/api/hub/items/{TestHub.ITEM_ID}", headers=auth_headers, timeout=20
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # Verify deleted (PATCH returns 404)
        r = api_client.patch(
            f"{BASE_URL}/api/hub/items/{TestHub.ITEM_ID}",
            json={"price": 1.0},
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 404

    def test_public_hub_no_auth(self, api_client):
        # uses slug from earlier test
        if not TestHub.SLUG:
            pytest.skip("slug not available")
        r = requests.get(f"{BASE_URL}/api/public/hub/{TestHub.SLUG}", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["slug"] == TestHub.SLUG
        assert "company" in body
        assert "items" in body

    def test_hub_extract_text(self, api_client, auth_headers):
        text = (
            "Le Domaine Test propose deux vins : un Bordeaux rouge AOC 2022 à 19,50 € "
            "issu de l'agriculture biologique, et un blanc sec Sauvignon 2023 à 14 €. "
            "Tous deux produits sur 12 hectares en Gironde."
        )
        r = api_client.post(
            f"{BASE_URL}/api/hub/extract",
            json={"source_type": "text", "source": text},
            headers=auth_headers,
            timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("products_created", 0) >= 1, body
        assert isinstance(body.get("items"), list) and len(body["items"]) >= 1


# ---------- CRM ----------
class TestCRM:
    def test_list_contacts(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/crm/contacts", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # Either a list directly or { items: [...] }
        if isinstance(body, dict):
            assert "items" in body or "contacts" in body
        else:
            assert isinstance(body, list)


# ---------- Wallet ----------
class TestWalletCheckout:
    def test_packs(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/wallet/packs", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        packs = body.get("packs") or []
        ids = {p.get("id") for p in packs}
        assert {"starter", "growth", "pro"}.issubset(ids), f"Missing pack ids: {ids}"

    def test_checkout_returns_stripe_test_url(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/wallet/checkout",
            json={
                "pack_id": "starter",
                "success_url": "https://example.com/s",
                "cancel_url": "https://example.com/c",
            },
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        url = body.get("checkout_url") or ""
        assert url.startswith("https://checkout.stripe.com/c/pay/cs_test_"), f"Not a TEST Stripe URL: {url}"


# ---------- Stripe webhook ----------
def _sign_stripe_payload(payload_bytes: bytes, secret: str, ts: int = None) -> str:
    ts = ts or int(time.time())
    signed = f"{ts}.{payload_bytes.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class TestStripeWebhook:
    EVENT_ID = f"evt_test_{uuid.uuid4().hex[:10]}"
    SESSION_ID = "cs_test_TESTWEBHOOK1"

    def test_no_signature_returns_400(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        assert "invalid webhook signature" in r.text.lower()

    def test_forged_signature_returns_400(self, api_client):
        body = b'{"id":"evt_forged","type":"checkout.session.completed"}'
        r = api_client.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": "t=1700000000,v1=deadbeef",
            },
            timeout=20,
        )
        assert r.status_code == 400, r.text

    def test_valid_signature_credits_user(self, api_client, mongo, user_id):
        # Snapshot credits + clean prior fixtures
        before_doc = mongo.users.find_one({"user_id": user_id}, {"credits": 1})
        credits_before = (before_doc or {}).get("credits", 0)

        # Remove any prior event/session rows so we test fresh idempotency
        mongo.stripe_events.delete_many({"event_id": TestStripeWebhook.EVENT_ID})
        mongo.wallet_events.delete_many({"stripe_session_id": TestStripeWebhook.SESSION_ID})

        event_payload = {
            "id": TestStripeWebhook.EVENT_ID,
            "object": "event",
            "type": "checkout.session.completed",
            "api_version": "2024-06-20",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": TestStripeWebhook.SESSION_ID,
                    "object": "checkout.session",
                    "metadata": {
                        "user_id": user_id,
                        "pack_id": "starter",
                        "credits": "100",
                    },
                }
            },
        }
        body = json.dumps(event_payload, separators=(",", ":")).encode()
        sig = _sign_stripe_payload(body, STRIPE_WEBHOOK_SECRET)
        r = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=body,
            headers={"Content-Type": "application/json", "Stripe-Signature": sig},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body_json = r.json()
        assert body_json.get("received") is True
        assert body_json.get("duplicate") is not True

        # Verify credits incremented by 100
        after = mongo.users.find_one({"user_id": user_id}, {"credits": 1})
        credits_after = (after or {}).get("credits", 0)
        assert credits_after == credits_before + 100, (
            f"Credits did not increment by 100: {credits_before} → {credits_after}"
        )

        # Verify wallet_event row written
        we = mongo.wallet_events.find_one({"stripe_session_id": TestStripeWebhook.SESSION_ID})
        assert we is not None
        assert we["credits"] == 100
        assert we["user_id"] == user_id

    def test_replay_is_idempotent(self, api_client, mongo, user_id):
        before = mongo.users.find_one({"user_id": user_id}, {"credits": 1}).get("credits", 0)

        event_payload = {
            "id": TestStripeWebhook.EVENT_ID,  # same event id → idempotent
            "object": "event",
            "type": "checkout.session.completed",
            "api_version": "2024-06-20",
            "created": int(time.time()),
            "data": {
                "object": {
                    "id": TestStripeWebhook.SESSION_ID,
                    "object": "checkout.session",
                    "metadata": {
                        "user_id": user_id,
                        "pack_id": "starter",
                        "credits": "100",
                    },
                }
            },
        }
        body = json.dumps(event_payload, separators=(",", ":")).encode()
        sig = _sign_stripe_payload(body, STRIPE_WEBHOOK_SECRET)
        r = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            data=body,
            headers={"Content-Type": "application/json", "Stripe-Signature": sig},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body_json = r.json()
        assert body_json.get("received") is True
        assert body_json.get("duplicate") is True, f"Expected duplicate flag: {body_json}"

        after = mongo.users.find_one({"user_id": user_id}, {"credits": 1}).get("credits", 0)
        assert after == before, f"Credits changed on replay! {before} → {after}"

    def test_cleanup_event_doc(self, mongo):
        # Cleanup the test event so future re-runs work
        mongo.stripe_events.delete_many({"event_id": TestStripeWebhook.EVENT_ID})
        mongo.wallet_events.delete_many({"stripe_session_id": TestStripeWebhook.SESSION_ID})


# ---------- Rate limit on /api/coach/message (30/min) ----------
class TestRateLimit:
    @pytest.mark.timeout(180)
    def test_coach_rate_limit_429(self, auth_headers):
        # Fire 40 concurrent short messages — the in-memory per-user limiter
        # raises 429 BEFORE the LLM is called once the 30/min cap is hit,
        # so excess requests return ~instantly.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _post(i: int):
            try:
                return requests.post(
                    f"{BASE_URL}/api/coach/message",
                    json={"message": f"ping {i}", "language": "fr"},
                    headers=auth_headers,
                    timeout=90,
                ).status_code
            except Exception as e:
                return f"err:{e}"

        statuses = []
        with ThreadPoolExecutor(max_workers=15) as ex:
            futures = [ex.submit(_post, i) for i in range(40)]
            for f in as_completed(futures):
                statuses.append(f.result())

        count_429 = sum(1 for s in statuses if s == 429)
        count_200 = sum(1 for s in statuses if s == 200)
        assert count_429 >= 1, f"Never hit 429 across 40 concurrent hits, saw: {statuses}"
        # Sanity: we should still see plenty of successful responses (cap=30)
        assert count_200 >= 1, f"No successful responses at all: {statuses}"


# ---------- Profile auto-extract ----------
class TestProfileAutoExtract:
    def test_target_countries_learned(self, api_client, auth_headers, mongo, user_id):
        # Clear target_countries first so the field is "missing"
        mongo.users.update_one(
            {"user_id": user_id},
            {"$set": {"business_profile.target_countries": []}},
        )
        r = api_client.post(
            f"{BASE_URL}/api/profile/auto-extract",
            json={"message": "Nous exportons aux États-Unis et au Japon", "language": "fr"},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        learned = body.get("learned_fields") or []
        assert "target_countries" in learned, f"target_countries not learned: {body}"
