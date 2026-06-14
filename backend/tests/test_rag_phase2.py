"""Phase 2 — RAG (Retrieval-Augmented Generation) end-to-end tests.

Covers:
- Regression of core endpoints
- RAG feature-gating (free plan → 402)
- RAG ingest (text, DOCX, URL) + list + search + delete on Pro plan
- RAG quota enforcement (rag_max_docs=5)
- Admin RAG (X-Admin-Key, global scope)
- Global docs visible to regular users
- Coach RAG context injection

Cleanup: reverts test user to free plan, deletes all rag_documents / rag_chunks
inserted by this run.
"""
from __future__ import annotations

import io
import os
import time
from typing import Any, Dict, List

import pytest
import requests

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"
ADMIN_KEY = "etoh_admin_b7a3e9d2f1c8a45e6b9d2f4a8c1e5b7d9f3a6c2e8b4d1f7a9c3e6b5d8f2a4c7e"
TEST_EMAIL = "vigneron@etoh-test.com"
TEST_PASSWORD = "WineLover2026"

# Track ids to clean up at the end
_created_user_doc_ids: List[str] = []
_created_admin_doc_ids: List[str] = []


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
    """Promote test user to Pro before tests; revert + cleanup after."""
    users = mongo_db["users"]
    # Snapshot original
    user_doc = users.find_one({"email": TEST_EMAIL}, {"subscription": 1, "_id": 0})
    original_sub = user_doc.get("subscription") if user_doc else None
    users.update_one(
        {"email": TEST_EMAIL},
        {"$set": {"subscription": {"plan_id": "pro", "status": "active"}}},
    )
    yield
    # ---- Teardown ----
    # Restore original subscription
    if original_sub is None:
        users.update_one({"email": TEST_EMAIL}, {"$unset": {"subscription": ""}})
    else:
        users.update_one({"email": TEST_EMAIL}, {"$set": {"subscription": original_sub}})

    # Delete all rag docs created during this run (user + global)
    all_doc_ids = list(set(_created_user_doc_ids + _created_admin_doc_ids))
    if all_doc_ids:
        mongo_db["rag_chunks"].delete_many({"doc_id": {"$in": all_doc_ids}})
        mongo_db["rag_documents"].delete_many({"doc_id": {"$in": all_doc_ids}})

    # Belt-and-suspenders: also wipe any docs left tagged "TEST_" or owned by this user
    user = users.find_one({"email": TEST_EMAIL}, {"user_id": 1, "_id": 0}) or {}
    if user.get("user_id"):
        # Only delete docs from this test run (uploaded_by admin or owned by this user with TEST_ prefix)
        leftover = list(mongo_db["rag_documents"].find(
            {"$or": [
                {"user_id": user["user_id"]},
                {"meta.uploaded_by": "admin", "name": {"$regex": "^TEST_"}},
            ]},
            {"doc_id": 1, "_id": 0},
        ))
        leftover_ids = [d["doc_id"] for d in leftover if d.get("doc_id")]
        if leftover_ids:
            mongo_db["rag_chunks"].delete_many({"doc_id": {"$in": leftover_ids}})
            mongo_db["rag_documents"].delete_many({"doc_id": {"$in": leftover_ids}})


def _docx_bytes(text: str) -> bytes:
    """Build a tiny DOCX in-memory with the given text."""
    from docx import Document
    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestARegression:
    """Sanity: confirm previous endpoints still work after the core/ + admin
    router refactor."""

    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=20)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_auth_me(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("email") == TEST_EMAIL

    def test_admin_health(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/health", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_admin_health_no_key(self):
        r = requests.get(f"{BASE_URL}/api/admin/health", timeout=20)
        assert r.status_code == 401

    def test_admin_metrics_summary(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/metrics/summary", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_subscription_plans(self):
        r = requests.get(f"{BASE_URL}/api/subscription/plans", timeout=20)
        assert r.status_code == 200
        plans = r.json().get("plans") or r.json()
        assert plans, "no plans returned"

    def test_hub_me(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hub/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_public_hub_domaine_test(self):
        r = requests.get(f"{BASE_URL}/api/public/hub/domaine-test", timeout=20)
        # Either configured (200) or not yet created (404) — both acceptable, but should NOT be 500
        assert r.status_code in (200, 404), r.text

    def test_wallet_packs(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/wallet/packs", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_enrich_ean(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/enrich/ean/3017620422003", headers=auth_headers, timeout=30
        )
        assert r.status_code == 200, r.text


class TestBRagFreePlanGating:
    """Free-plan user MUST be rejected with 402."""

    def test_rag_text_blocked_for_free_plan(self, mongo_db, auth_headers):
        # Temporarily demote to free
        mongo_db["users"].update_one({"email": TEST_EMAIL}, {"$unset": {"subscription": ""}})
        try:
            r = requests.post(
                f"{BASE_URL}/api/rag/documents/text",
                headers=auth_headers,
                json={"text": "x" * 200, "name": "TEST_free_attempt"},
                timeout=30,
            )
            assert r.status_code == 402, f"expected 402, got {r.status_code} {r.text}"
            assert "RAG indisponible" in r.text or "RAG" in r.text
        finally:
            # Re-promote so subsequent tests still pass
            mongo_db["users"].update_one(
                {"email": TEST_EMAIL},
                {"$set": {"subscription": {"plan_id": "pro", "status": "active"}}},
            )


class TestCRagProFlow:
    """End-to-end RAG flow on Pro plan."""

    cascade_text = (
        "Le Domaine de Cascade produit un rosé bio en Provence depuis 1987. "
        "Notre cuvée Aurore est élevée 6 mois sur lies fines. "
        "Production annuelle de 12000 bouteilles. "
        "Distribution: CHR Sud-Est, USA, Japon, Suisse. "
        "Certifications: AB depuis 2010, Demeter en cours."
    )

    def test_ingest_text(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/documents/text",
            headers=auth_headers,
            json={"text": self.cascade_text, "name": "TEST_Plaquette_Cascade"},
            timeout=90,  # First call triggers ~3s model load
        )
        assert r.status_code == 200, f"text ingest failed: {r.status_code} {r.text}"
        data = r.json()
        assert "doc_id" in data
        assert data["chunk_count"] >= 1
        assert data["char_count"] >= 200
        _created_user_doc_ids.append(data["doc_id"])

    def test_ingest_docx(self, auth_headers, token):
        docx_bytes = _docx_bytes(
            "TEST_DOCX_Cascade\n"
            "Le Domaine de Cascade a aussi un partenariat avec un importateur en Allemagne. "
            "Nos vins bio sont distribués via Vinatis et la Grande Épicerie de Paris. "
            "Notre équipe commerciale travaille sur l'ouverture du marché coréen pour 2026."
        )
        files = {"file": ("TEST_partners.docx", docx_bytes,
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r = requests.post(
            f"{BASE_URL}/api/rag/documents",
            headers={"Authorization": f"Bearer {token}"},  # no Content-Type for multipart
            files=files,
            timeout=90,
        )
        assert r.status_code == 200, f"docx ingest failed: {r.status_code} {r.text}"
        data = r.json()
        assert "doc_id" in data
        assert data["source_type"] == "docx"
        _created_user_doc_ids.append(data["doc_id"])

    def test_ingest_url(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/documents/url",
            headers=auth_headers,
            json={"url": "https://en.wikipedia.org/wiki/Wine", "name": "TEST_wiki_wine"},
            timeout=120,
        )
        assert r.status_code == 200, f"url ingest failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("chunk_count", 0) > 0
        _created_user_doc_ids.append(data["doc_id"])

    def test_list_documents_contains_all(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rag/documents", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        docs = r.json()["documents"]
        ids = {d.get("doc_id") for d in docs}
        for did in _created_user_doc_ids:
            assert did in ids, f"missing {did} in list"

    def test_search_returns_relevant_chunks(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/rag/search",
            headers=auth_headers,
            json={"query": "marchés export", "top_k": 3},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        results = body.get("results") or []
        assert len(results) > 0, "no results"
        top = results[0]
        assert top["score"] > 0.1, f"top score too low: {top['score']}"
        # First or any of top-3 should mention export markets
        all_text = " ".join((h.get("text") or "") for h in results)
        assert any(kw in all_text for kw in ("USA", "Japon", "Suisse")), \
            f"none of USA/Japon/Suisse found in top results: {all_text[:300]}"

    def test_coach_uses_rag_context(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/coach/message",
            headers=auth_headers,
            json={"message": "Sur quels marchés est-ce que je dois prospecter ?",
                  "language": "fr"},
            timeout=120,
        )
        assert r.status_code == 200, f"coach failed: {r.status_code} {r.text}"
        body = r.json()
        reply = (body.get("reply") or body.get("message") or "").upper()
        # At least one of the RAG-injected terms should surface in the reply
        keywords = ["USA", "JAPON", "SUISSE", "SUD-EST", "AB", "DEMETER", "BIO", "ALLEMAGNE", "CORÉE", "VINATIS"]
        hits = [k for k in keywords if k in reply]
        assert hits, f"reply contains no RAG-derived keywords: {reply[:400]}"

    def test_delete_document(self, auth_headers, mongo_db):
        # Delete the first user doc and confirm chunks were also removed
        target = _created_user_doc_ids[0]
        r = requests.delete(
            f"{BASE_URL}/api/rag/documents/{target}", headers=auth_headers, timeout=30
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Confirm doc + chunks gone
        leftover_doc = mongo_db["rag_documents"].count_documents({"doc_id": target})
        leftover_chunks = mongo_db["rag_chunks"].count_documents({"doc_id": target})
        assert leftover_doc == 0
        assert leftover_chunks == 0
        _created_user_doc_ids.remove(target)

        # And list should now exclude it
        r = requests.get(f"{BASE_URL}/api/rag/documents", headers=auth_headers, timeout=30)
        ids = {d.get("doc_id") for d in r.json()["documents"]}
        assert target not in ids


class TestDRagQuota:
    """Pro plan has rag_max_docs=5. We already inserted 2 in TestC (after the
    text+docx+url=3, but one was deleted → 2 remaining). Insert until we hit 5,
    the 6th must 402."""

    def test_quota_enforced(self, auth_headers, mongo_db):
        # Count current user docs
        user_id = mongo_db["users"].find_one({"email": TEST_EMAIL}, {"user_id": 1})["user_id"]
        current = mongo_db["rag_documents"].count_documents({"user_id": user_id})
        # Fill up to 5
        slots_left = 5 - current
        assert slots_left >= 0
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
        assert "Quota" in r.text or "quota" in r.text


class TestEAdminRag:
    """Admin RAG endpoints — X-Admin-Key required, global docs visible to all
    users."""

    def test_admin_ingest_url_global(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/admin/rag/documents/url",
            headers=admin_headers,
            json={"url": "https://en.wikipedia.org/wiki/Champagne",
                  "name": "TEST_admin_champagne",
                  "scope": "global"},
            timeout=120,
        )
        assert r.status_code == 200, f"admin url failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("scope") == "global"
        assert "doc_id" in data
        _created_admin_doc_ids.append(data["doc_id"])

    def test_admin_list_documents(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/rag/documents", headers=admin_headers, timeout=30
        )
        assert r.status_code == 200, r.text
        docs = r.json()["documents"]
        ids = {d.get("doc_id") for d in docs}
        # Should include the global doc just ingested
        for did in _created_admin_doc_ids:
            assert did in ids

    def test_admin_no_key_blocked(self):
        r = requests.get(f"{BASE_URL}/api/admin/rag/documents", timeout=20)
        assert r.status_code == 401

        r2 = requests.post(
            f"{BASE_URL}/api/admin/rag/documents/url",
            json={"url": "https://example.com", "scope": "global"},
            timeout=20,
        )
        assert r2.status_code == 401

    def test_global_doc_visible_to_user(self, auth_headers):
        """Regular user listing should include the global doc."""
        r = requests.get(f"{BASE_URL}/api/rag/documents", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        docs = r.json()["documents"]
        ids = {d.get("doc_id") for d in docs}
        for did in _created_admin_doc_ids:
            assert did in ids, f"global doc {did} not visible to regular user"

    def test_admin_delete_document(self, admin_headers, mongo_db):
        target = _created_admin_doc_ids[0]
        r = requests.delete(
            f"{BASE_URL}/api/admin/rag/documents/{target}",
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        # Confirm gone
        assert mongo_db["rag_documents"].count_documents({"doc_id": target}) == 0
        assert mongo_db["rag_chunks"].count_documents({"doc_id": target}) == 0
        _created_admin_doc_ids.remove(target)
