import os
import pytest
import requests

BASE_URL = "https://ai-coach-autopilot.preview.emergentagent.com"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_token(api_client):
    """Login with seeded test user and return JWT."""
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "vigneron@etoh-test.com", "password": "WineLover2026"},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
