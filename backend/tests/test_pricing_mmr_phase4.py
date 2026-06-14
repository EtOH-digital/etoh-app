"""Iteration 8 — Phase 4 Pricing engine + Phase 5 MMR rerank tests.

Covers:
- GET /api/pricing/defaults
- POST /api/pricing/compute (success, negative, no auth, export)
- PUT /api/pricing/products/{id} (save snapshot + 404)
- MMR rerank diversity in /api/rag/search
- Regression sample (root, auth/me, admin, plans, hub/me, public/hub, enrich, coach RAG)

Cleanup: revert user to free, delete pricing snapshots, rag docs/chunks, hub items
created by this run.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest
import requests

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"
ADMIN_KEY = "etoh_admin_b7a3e9d2f1c8a45e6b9d2f4a8c1e5b7d9f3a6c2e8b4d1f7a9c3e6b5d8f2a4c7e"
TEST_EMAIL = "vigneron@etoh-test.com"
TEST_PASSWORD = "WineLover2026"

_created_user_doc_ids: List[str] = []
_created_hub_item_ids: List[str] = []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def mongo_db():
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "etoh_db")
    client = MongoClient(mongo_url)
    yield client[db_name]
    client.close()


@pytest.fixture(scope="module")
def token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    return {"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def promote_to_pro_and_cleanup(mongo_db):
    users = mongo_db["users"]
    user_doc = users.find_one({"email": TEST_EMAIL}, {"subscription": 1, "_id": 0})
    original_sub = user_doc.get("subscription") if user_doc else None
    users.update_one(
        {"email": TEST_EMAIL},
        {"$set": {"subscription": {"plan_id": "pro", "status": "active"}}},
    )
    yield
    # ---- Teardown ----
    if original_sub is None:
        users.update_one({"email": TEST_EMAIL}, {"$unset": {"subscription": ""}})
    else:
        users.update_one({"email": TEST_EMAIL}, {"$set": {"subscription": original_sub}})

    if _created_user_doc_ids:
        mongo_db["rag_chunks"].delete_many({"doc_id": {"$in": _created_user_doc_ids}})
        mongo_db["rag_documents"].delete_many({"doc_id": {"$in": _created_user_doc_ids}})

    if _created_hub_item_ids:
        mongo_db["hub_items"].delete_many({"id": {"$in": _created_hub_item_ids}})

    user = users.find_one({"email": TEST_EMAIL}, {"user_id": 1, "_id": 0}) or {}
    if user.get("user_id"):
        leftover = list(mongo_db["rag_documents"].find(
            {"user_id": user["user_id"]}, {"doc_id": 1, "_id": 0},
        ))
        leftover_ids = [d["doc_id"] for d in leftover if d.get("doc_id")]
        if leftover_ids:
            mongo_db["rag_chunks"].delete_many({"doc_id": {"$in": leftover_ids}})
            mongo_db["rag_documents"].delete_many({"doc_id": {"$in": leftover_ids}})
        # Hub items created with TEST_ prefix
        mongo_db["hub_items"].delete_many(
            {"user_id": user["user_id"], "name": {"$regex": "^TEST_"}}
        )


# ---------------------------------------------------------------------------
# A. PRICING DEFAULTS
# ---------------------------------------------------------------------------
class TestAPricingDefaults:
    def test_defaults_returns_5_channels(self):
        r = requests.get(f"{BASE_URL}/api/pricing/defaults", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        channels = body.get("channels")
        assert isinstance(channels, list) and len(channels) == 5, f"got {channels}"
        ids = {c["id"] for c in channels}
        assert ids == {"direct", "chr", "caviste", "distrib", "export"}, ids
        for c in channels:
            assert "margin_pct" in c, f"missing margin_pct in {c}"
            assert isinstance(c["margin_pct"], (int, float))


# ---------------------------------------------------------------------------
# B. PRICING COMPUTE
# ---------------------------------------------------------------------------
class TestBPricingCompute:
    def test_compute_no_auth_401(self):
        r = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            json={"base_cost_eur": 4.5},
            timeout=20,
        )
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text}"

    def test_compute_success(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=auth_headers,
            json={"base_cost_eur": 4.5},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cost"]["base"] == 4.5
        assert body["vat_pct"] == 20
        channels = body["channels"]
        assert len(channels) == 5
        for c in channels:
            assert c["producer_price_ht"] > 4.5, f"{c['id']} producer_price_ht={c['producer_price_ht']} not > 4.5"
            assert c["retail_price_ttc"] > c["producer_price_ht"], (
                f"{c['id']} retail_price_ttc={c['retail_price_ttc']} not > producer_price_ht={c['producer_price_ht']}"
            )
        # Direct channel retail ~ 13.50 (cost 4.5, margin 60%, retail_markup 0, dist 0, VAT 20%)
        # producer = 4.5 / 0.4 = 11.25; partner = 11.25; retail = 11.25 * 1.0 * 1.2 = 13.5
        direct = next(c for c in channels if c["id"] == "direct")
        assert abs(direct["retail_price_ttc"] - 13.5) < 0.05, (
            f"direct retail expected ~13.50 got {direct['retail_price_ttc']}"
        )

    def test_compute_export_landed_cost(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=auth_headers,
            json={"base_cost_eur": 4.5, "shipping_eur": 2.0, "duty_pct": 15.0},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        export = next(c for c in body["channels"] if c["id"] == "export")
        # landed = (4.5 + 2) * 1.15 * 1.03 = 7.69925 ≈ 7.70
        assert abs(export["landed_cost_ht"] - 7.70) < 0.05, (
            f"export landed_cost expected ~7.70 got {export['landed_cost_ht']}"
        )
        # producer_price = 7.70 / (1 - 0.30) = 10.99...
        # vs no-shipping case where producer = 4.5/0.7 = 6.43
        direct_resp = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=auth_headers,
            json={"base_cost_eur": 4.5},
            timeout=30,
        )
        export_no_ship = next(c for c in direct_resp.json()["channels"] if c["id"] == "export")
        assert export["producer_price_ht"] > export_no_ship["producer_price_ht"], (
            f"with shipping+duty, producer price should be higher: "
            f"{export['producer_price_ht']} vs {export_no_ship['producer_price_ht']}"
        )

    def test_compute_negative_base_cost(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=auth_headers,
            json={"base_cost_eur": -1},
            timeout=20,
        )
        assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code} {r.text}"


# ---------------------------------------------------------------------------
# C. PRICING SAVE
# ---------------------------------------------------------------------------
class TestCPricingSave:
    def test_save_pricing_404_unknown_id(self, auth_headers):
        r = requests.put(
            f"{BASE_URL}/api/pricing/products/UNKNOWN_ID_DOES_NOT_EXIST",
            headers=auth_headers,
            json={
                "product_id": "UNKNOWN_ID_DOES_NOT_EXIST",
                "pricing": {"channels": []},
                "base_cost_eur": 4.5,
            },
            timeout=20,
        )
        assert r.status_code == 404, f"expected 404 got {r.status_code} {r.text}"

    def test_save_pricing_success(self, auth_headers, mongo_db):
        # 1) Create a Hub product
        create = requests.post(
            f"{BASE_URL}/api/hub/items",
            headers=auth_headers,
            json={"type": "product", "name": "TEST_Pricing_Product"},
            timeout=20,
        )
        assert create.status_code == 200, create.text
        product = create.json()
        product_id = product["id"]
        _created_hub_item_ids.append(product_id)

        # 2) Compute prices
        comp = requests.post(
            f"{BASE_URL}/api/pricing/compute",
            headers=auth_headers,
            json={"base_cost_eur": 4.5},
            timeout=30,
        )
        snapshot = comp.json()

        # 3) Save
        r = requests.put(
            f"{BASE_URL}/api/pricing/products/{product_id}",
            headers=auth_headers,
            json={
                "product_id": product_id,
                "pricing": snapshot,
                "base_cost_eur": 4.5,
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # 4) Verify persistence in MongoDB
        doc = mongo_db["hub_items"].find_one({"id": product_id})
        assert doc is not None
        pricing = doc.get("pricing") or {}
        assert pricing.get("base_cost_eur") == 4.5
        assert pricing.get("snapshot") is not None
        assert "channels" in pricing["snapshot"]


# ---------------------------------------------------------------------------
# D. MMR RAG SEARCH
# ---------------------------------------------------------------------------
class TestDMmrRagSearch:
    """Ingest one long generic doc + one short specific doc, verify MMR rerank
    surfaces the short specific doc in top_k=4."""

    aurore_text = (
        "Notre cuvée Aurore 2024 est un rosé bio à 12.5 euros TTC, produit en "
        "Provence par le Domaine de Cascade. Cuvée Aurore est élevée 6 mois sur "
        "lies fines, certifiée AB depuis 2010."
    )

    def test_ingest_long_wiki(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/documents/url",
            headers=auth_headers,
            json={"url": "https://fr.wikipedia.org/wiki/Vin", "name": "TEST_wiki_vin"},
            timeout=180,
        )
        assert r.status_code == 200, f"wiki ingest failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("chunk_count", 0) > 5, f"expected >5 chunks, got {body}"
        _created_user_doc_ids.append(body["doc_id"])

    def test_ingest_short_aurore(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/documents/text",
            headers=auth_headers,
            json={"text": self.aurore_text, "name": "TEST_Domaine_de_Cascade_Aurore"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        _created_user_doc_ids.append(r.json()["doc_id"])

    def test_mmr_search_aurore_present(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/search",
            headers=auth_headers,
            json={"query": "cuvée Aurore prix", "top_k": 4},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        results = r.json().get("results") or []
        assert len(results) > 0
        # At least one result must mention Cascade or Aurore
        found = any(
            ("Cascade" in (h.get("doc_name") or "")) or ("Aurore" in (h.get("text") or ""))
            for h in results
        )
        assert found, (
            "MMR did not surface the small specific Aurore doc. Returned: "
            + " | ".join(f"{h.get('doc_name')}::{(h.get('text') or '')[:80]}" for h in results)
        )

    def test_mmr_diversity_vin_bio(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/search",
            headers=auth_headers,
            json={"query": "vin bio", "top_k": 5},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        results = r.json().get("results") or []
        assert len(results) >= 2, f"expected >=2 results, got {len(results)}"
        doc_ids = {h.get("doc_id") for h in results}
        assert len(doc_ids) >= 2, (
            f"MMR diversity check failed — all {len(results)} chunks came from "
            f"single doc {doc_ids}"
        )


# ---------------------------------------------------------------------------
# E. RAG QUOTA regression (rag_max_docs=5)
# ---------------------------------------------------------------------------
class TestERagQuotaRegression:
    def test_quota_402_after_5(self, auth_headers, mongo_db):
        user_id = mongo_db["users"].find_one({"email": TEST_EMAIL}, {"user_id": 1})["user_id"]
        current = mongo_db["rag_documents"].count_documents({"user_id": user_id})
        slots_left = 5 - current
        if slots_left < 0:
            pytest.skip(f"already over quota ({current} docs), can't test")
        for i in range(slots_left):
            r = requests.post(
                f"{BASE_URL}/api/rag/documents/text",
                headers=auth_headers,
                json={
                    "text": f"TEST_quota_filler #{i} — " + ("a" * 200),
                    "name": f"TEST_quota_filler_{i}",
                },
                timeout=60,
            )
            assert r.status_code == 200, f"filler #{i} failed: {r.status_code} {r.text}"
            _created_user_doc_ids.append(r.json()["doc_id"])

        # Now 6th must be 402
        r = requests.post(
            f"{BASE_URL}/api/rag/documents/text",
            headers=auth_headers,
            json={"text": "TEST_quota_over — " + ("b" * 200), "name": "TEST_quota_over"},
            timeout=60,
        )
        assert r.status_code == 402, f"expected 402 over-quota, got {r.status_code} {r.text}"


# ---------------------------------------------------------------------------
# F. REGRESSION
# ---------------------------------------------------------------------------
class TestFRegression:
    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=20)
        assert r.status_code == 200

    def test_auth_me(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json().get("email") == TEST_EMAIL

    def test_admin_health(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/health", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_admin_metrics_summary(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/metrics/summary", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_subscription_plans(self):
        r = requests.get(f"{BASE_URL}/api/subscription/plans", timeout=20)
        assert r.status_code == 200

    def test_hub_me(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hub/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200

    def test_public_hub_invalid_404(self):
        r = requests.get(f"{BASE_URL}/api/public/hub/INVALID-SLUG-DOES-NOT-EXIST", timeout=20)
        assert r.status_code == 404

    def test_enrich_ean(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/enrich/ean/3017620422003", headers=auth_headers, timeout=30
        )
        assert r.status_code == 200
