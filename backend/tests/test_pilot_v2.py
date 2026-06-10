"""EtOH Pilot v2 + credits test suite — covers /credits/me, /pilot/search, /pilot/draft,
/pilot/send-email, /pilot/open-channel, /pilot/searches, /pilot/actions, and 402 when credits exhausted.
"""
import os
import uuid
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "etoh_db")

TEST_EMAIL = "vigneron@etoh-test.com"
TEST_PASSWORD = "WineLover2026"


# ---------- Helpers ----------
@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def session_data():
    """Login once and reuse token + user_id across this module."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    token = d["access_token"]
    user_id = d["user"]["user_id"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return {"session": s, "token": token, "user_id": user_id}


def _set_credits(mongo_db, user_id, value):
    mongo_db.users.update_one({"user_id": user_id}, {"$set": {"credits": int(value)}})


def _get_credits(mongo_db, user_id):
    u = mongo_db.users.find_one({"user_id": user_id}, {"_id": 0, "credits": 1})
    return int(u.get("credits", 0)) if u else 0


# ---------- Credits ----------
class TestCredits:
    def test_credits_me_shape(self, session_data, mongo_db):
        # Ensure plenty of credits to start
        _set_credits(mongo_db, session_data["user_id"], 50)
        r = session_data["session"].get(f"{BASE_URL}/api/credits/me", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["credits"] == 50
        assert d["credit_price_eur"] == 0.099
        assert d["action_cost"] == 1

    def test_credits_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/credits/me", timeout=10)
        assert r.status_code == 401


# ---------- Pilot Search ----------
class TestPilotSearch:
    def test_search_returns_8_targets(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 50)
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/search",
            json={"query": "cavistes paris vins nature", "language": "fr"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "search_id" in d
        assert d["query"] == "cavistes paris vins nature"
        assert "interpretation" in d
        assert isinstance(d["interpretation"], str)
        assert "targets" in d
        targets = d["targets"]
        assert isinstance(targets, list)
        assert len(targets) == 8, f"Expected 8 targets, got {len(targets)}"
        # Validate target shape on first
        t0 = targets[0]
        for k in ("id", "name", "type", "city", "snippet"):
            assert k in t0, f"Missing key {k} in target: {t0.keys()}"
        # presence of contact fields (not authenticity)
        assert any(k in t0 for k in ("email", "phone", "linkedin_url"))
        assert "tags" in t0 and isinstance(t0["tags"], list)
        # ids must be stable t1..t8
        ids = [t["id"] for t in targets]
        assert ids == [f"t{i+1}" for i in range(8)]
        # Search is FREE - credits should be unchanged
        creds = _get_credits(mongo_db, session_data["user_id"])
        assert creds == 50, f"Search should be free but credits became {creds}"

        TestPilotSearch._search_id = d["search_id"]
        TestPilotSearch._targets = targets

    def test_search_requires_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/pilot/search",
            json={"query": "test", "language": "fr"},
            timeout=10,
        )
        assert r.status_code == 401


# ---------- Pilot Draft ----------
class TestPilotDraft:
    def test_draft_email_has_subject(self, session_data, mongo_db):
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[0]["id"]
        before = _get_credits(mongo_db, session_data["user_id"])
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/draft",
            json={"search_id": sid, "target_id": tid, "channel": "email", "language": "fr"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["target_id"] == tid
        assert d["channel"] == "email"
        assert d["subject"] is not None and len(d["subject"]) > 0
        assert len(d["body"]) > 50
        # Draft is FREE
        after = _get_credits(mongo_db, session_data["user_id"])
        assert after == before, "Draft should not deduct credits"
        TestPilotDraft._email_draft = d

    def test_draft_whatsapp_no_subject(self, session_data):
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[1]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/draft",
            json={"search_id": sid, "target_id": tid, "channel": "whatsapp", "language": "fr"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["channel"] == "whatsapp"
        assert d["subject"] is None
        assert len(d["body"]) > 20

    def test_draft_linkedin_no_subject(self, session_data):
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[2]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/draft",
            json={"search_id": sid, "target_id": tid, "channel": "linkedin", "language": "fr"},
            timeout=90,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["channel"] == "linkedin"
        assert d["subject"] is None
        assert len(d["body"]) > 30

    def test_draft_invalid_target_404(self, session_data):
        sid = TestPilotSearch._search_id
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/draft",
            json={"search_id": sid, "target_id": "tNOPE", "channel": "email", "language": "fr"},
            timeout=30,
        )
        assert r.status_code == 404


# ---------- Send Email & Credit Deduction ----------
class TestSendEmailAndCredits:
    def test_send_email_deducts_one_credit_mocked(self, session_data, mongo_db):
        # Set credits to known value
        _set_credits(mongo_db, session_data["user_id"], 20)
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[0]["id"]
        draft = TestPilotDraft._email_draft
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/send-email",
            json={
                "search_id": sid,
                "target_id": tid,
                "to_email": "TEST_recipient@example.com",
                "to_name": "Test Recipient",
                "subject": draft["subject"] or "Test subject",
                "body": draft["body"],
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["mocked"] is True, f"Expected mocked=True (no RESEND_API_KEY), got {d}"
        assert d["credits_remaining"] == 19, f"Expected 19 credits left, got {d['credits_remaining']}"
        # verify via /credits/me
        c = session_data["session"].get(f"{BASE_URL}/api/credits/me", timeout=10).json()
        assert c["credits"] == 19

    def test_open_whatsapp_deducts_one_credit(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 10)
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[1]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/open-channel",
            json={"search_id": sid, "target_id": tid, "channel": "whatsapp"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["credits_remaining"] == 9

    def test_open_linkedin_deducts_one_credit(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 5)
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[2]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/open-channel",
            json={"search_id": sid, "target_id": tid, "channel": "linkedin"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["credits_remaining"] == 4


# ---------- 402 Payment Required ----------
class TestInsufficientCredits:
    def test_send_email_402_when_zero_credits(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 0)
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[0]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/send-email",
            json={
                "search_id": sid,
                "target_id": tid,
                "to_email": "TEST_zero@example.com",
                "to_name": "Zero",
                "subject": "x",
                "body": "y",
            },
            timeout=20,
        )
        assert r.status_code == 402, f"Expected 402 when credits=0, got {r.status_code} {r.text}"
        # Credits must still be 0 (no negative)
        assert _get_credits(mongo_db, session_data["user_id"]) == 0

    def test_open_channel_402_when_zero_credits(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 0)
        sid = TestPilotSearch._search_id
        tid = TestPilotSearch._targets[0]["id"]
        r = session_data["session"].post(
            f"{BASE_URL}/api/pilot/open-channel",
            json={"search_id": sid, "target_id": tid, "channel": "whatsapp"},
            timeout=15,
        )
        assert r.status_code == 402


# ---------- Searches & Actions history ----------
class TestHistory:
    def test_pilot_searches_history(self, session_data):
        r = session_data["session"].get(f"{BASE_URL}/api/pilot/searches", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert isinstance(items, list)
        assert len(items) >= 1
        first = items[0]
        for k in ("id", "query", "target_count", "created_at"):
            assert k in first
        assert "_id" not in first

    def test_pilot_actions_log(self, session_data):
        r = session_data["session"].get(f"{BASE_URL}/api/pilot/actions", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert isinstance(items, list)
        # Should include at least: send_email, open_whatsapp, open_linkedin from earlier tests
        actions = {it["action"] for it in items}
        assert "send_email" in actions, f"Got actions: {actions}"
        assert "open_whatsapp" in actions
        assert "open_linkedin" in actions
        for it in items:
            assert it["cost"] == 1
            assert "_id" not in it


# ---------- Final: restore credits ----------
class TestRestore:
    def test_restore_credits_to_100(self, session_data, mongo_db):
        _set_credits(mongo_db, session_data["user_id"], 100)
        c = session_data["session"].get(f"{BASE_URL}/api/credits/me", timeout=10).json()
        assert c["credits"] == 100
