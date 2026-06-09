"""EtOH backend API test suite — covers auth, profile, home, coach, studio, pilot."""
import os
import time
import uuid
import requests
import pytest

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"


# ----- Health -----
class TestHealth:
    def test_root(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ----- Auth -----
class TestAuth:
    def test_signup_new_user(self, api_client):
        unique = uuid.uuid4().hex[:8]
        email = f"TEST_signup_{unique}@etoh-test.com"
        r = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json={"email": email, "password": "TestPass1234", "name": "TEST Signup"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"].lower() == email.lower()
        assert "_id" not in data["user"]
        # store for cleanup
        TestAuth._created_email = email
        TestAuth._created_token = data["access_token"]

    def test_signup_duplicate_fails(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/auth/signup",
            json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
            timeout=20,
        )
        assert r.status_code == 400

    def test_login_seeded_user(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
            timeout=20,
        )
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == "vigneron@etoh-test.com"
        assert "_id" not in data["user"]

    def test_login_invalid_password(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "vigneron@etoh-test.com", "password": "wrongpass"},
            timeout=20,
        )
        assert r.status_code == 400

    def test_me_requires_auth(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_with_token(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "vigneron@etoh-test.com"
        assert "_id" not in data


# ----- Profile -----
class TestProfile:
    def test_update_profile_persists(self, api_client, auth_headers):
        payload = {
            "business_name": "Domaine Test",
            "business_type": "winery",
            "region": "Bordeaux",
            "main_products": "Vins rouges AOC",
            "role": "Vigneron",
            "language": "fr",
        }
        r = api_client.put(
            f"{BASE_URL}/api/profile", json=payload, headers=auth_headers, timeout=20
        )
        assert r.status_code == 200, r.text
        data = r.json()
        bp = data.get("business_profile") or {}
        assert bp.get("business_name") == "Domaine Test"
        assert bp.get("region") == "Bordeaux"
        assert "_id" not in data

        # Verify via GET /me
        me = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15)
        assert me.status_code == 200
        assert me.json()["business_profile"]["business_name"] == "Domaine Test"

    def test_profile_requires_auth(self, api_client):
        r = api_client.put(f"{BASE_URL}/api/profile", json={"region": "x"}, timeout=10)
        assert r.status_code == 401


# ----- Home recommendations (AI) -----
class TestHome:
    def test_recommendations_returns_3(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/home/recommendations",
            json={"language": "fr"},
            headers=auth_headers,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "recommendations" in data
        recs = data["recommendations"]
        assert isinstance(recs, list)
        assert len(recs) == 3
        for rec in recs:
            assert "title" in rec
            assert "description" in rec
            assert "module" in rec
            assert rec["module"] in ("coach", "studio", "pilot")

    def test_recommendations_requires_auth(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/home/recommendations", json={"language": "fr"}, timeout=10
        )
        assert r.status_code == 401


# ----- Coach (multi-turn) -----
class TestCoach:
    def test_coach_message_and_persistence(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/coach/message",
            json={"message": "Comment vendre plus en restaurants ?", "language": "fr"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_id" in data
        assert "reply" in data
        assert len(data["reply"]) > 20
        TestCoach._session_id = data["session_id"]

    def test_coach_followup_keeps_session(self, api_client, auth_headers):
        sid = getattr(TestCoach, "_session_id", None)
        if not sid:
            pytest.skip("No session from previous test")
        r = api_client.post(
            f"{BASE_URL}/api/coach/message",
            json={"session_id": sid, "message": "Donne-moi un exemple de pitch.", "language": "fr"},
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid

    def test_coach_sessions_list(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/coach/sessions", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        # at least one session from prior tests
        assert len(data["sessions"]) >= 1
        # ensure no Mongo _id leaked
        for s in data["sessions"]:
            assert "_id" not in s

    def test_coach_requires_auth(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/coach/message",
            json={"message": "hi", "language": "fr"},
            timeout=10,
        )
        assert r.status_code == 401


# ----- Studio -----
class TestStudio:
    def test_generate_linkedin_post(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/studio/generate",
            json={
                "template": "linkedin_post",
                "brief": "Nouveau millésime 2024 Bordeaux",
                "tone": "premium",
                "language": "fr",
            },
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert data["template"] == "linkedin_post"
        assert len(data["content"]) > 50
        assert "_id" not in data

    def test_studio_history(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/studio/history", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert isinstance(items, list)
        if items:
            assert "_id" not in items[0]
            assert "content" in items[0]

    def test_studio_invalid_template(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/studio/generate",
            json={"template": "invalid_template", "brief": "x", "language": "fr"},
            headers=auth_headers,
            timeout=20,
        )
        assert r.status_code == 422


# ----- Pilot -----
class TestPilot:
    def test_pilot_plan_generation(self, api_client, auth_headers):
        r = api_client.post(
            f"{BASE_URL}/api/pilot/plan",
            json={
                "target_type": "restaurants",
                "region": "Paris",
                "product_focus": "Bordeaux rouge",
                "language": "fr",
            },
            headers=auth_headers,
            timeout=90,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        assert "plan" in data
        plan = data["plan"]
        assert "summary" in plan
        assert "targets" in plan
        assert "tasks" in plan
        assert isinstance(plan["targets"], list)
        assert isinstance(plan["tasks"], list)
        assert len(plan["targets"]) >= 3
        assert len(plan["tasks"]) >= 3
        assert "_id" not in data

    def test_pilot_history(self, api_client, auth_headers):
        r = api_client.get(f"{BASE_URL}/api/pilot/history", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert isinstance(items, list)
        if items:
            assert "_id" not in items[0]

    def test_pilot_requires_auth(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/pilot/plan",
            json={"target_type": "restaurants", "region": "Paris", "language": "fr"},
            timeout=10,
        )
        assert r.status_code == 401


# ----- Logout -----
class TestLogout:
    def test_logout(self, api_client, auth_headers):
        r = api_client.post(f"{BASE_URL}/api/auth/logout", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # JWT not in user_sessions table, so /me should still work with the token
        # (logout only invalidates Google session tokens). This is current behavior.
