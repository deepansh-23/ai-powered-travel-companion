"""Automated tests for CAPTCHA server-side verification (Section 33A-9).
"""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_captcha_config_endpoint():
    res = client.get("/api/captcha/config")
    assert res.status_code == 200
    data = res.json()
    assert "site_key" in data
    assert "enabled" in data


def test_captcha_verify_missing_token():
    res = client.post("/api/captcha/verify", json={"token": ""})
    assert res.status_code == 400
    assert "required" in res.json()["detail"].lower()


def test_captcha_verify_invalid_token():
    res = client.post("/api/captcha/verify", json={"token": "invalid-test-token"})
    assert res.status_code == 400
    assert "failed" in res.json()["detail"].lower() or "invalid" in res.json()["detail"].lower()


def test_captcha_verify_valid_token_mocked():
    with patch("app.services.captcha_service.captcha_service.verify_token", new_callable=AsyncMock) as mock_v:
        mock_v.return_value = {"success": True, "score": 0.9}
        res = client.post("/api/captcha/verify", json={"token": "valid_mock_token_123"})
        assert res.status_code == 200
        assert res.json()["status"] == "verified"


def test_captcha_fails_closed_in_live_mode_without_secret(monkeypatch):
    import asyncio
    from app.config import settings
    from app.services.captcha_service import captcha_service

    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", None)
    monkeypatch.setattr(settings, "MOCK_MODE", False)
    res = asyncio.run(captcha_service.verify_token("any-token"))
    assert res["success"] is False


# ---------------------------------------------------------------------------
# Real CAPTCHA session flow (provider keys configured)
# ---------------------------------------------------------------------------
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def captcha_on(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "site-key-123")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "secret-key-456")


def _fresh_client():
    from app.main import app

    return TestClient(app)


def _mock_verify(success=True):
    return patch(
        "app.services.captcha_service.captcha_service.verify_token",
        new_callable=AsyncMock,
        return_value={"success": success, "message": "CAPTCHA verification failed."},
    )


FEEDBACK = {"rating": 5, "comment": "great", "service_used": "itinerary"}


def test_config_exposes_only_public_data(captcha_on):
    cfg = _fresh_client().get("/api/captcha/config").json()
    assert cfg["enabled"] is True and cfg["site_key"] == "site-key-123"
    assert cfg["provider"] == "recaptcha" and "google.com/recaptcha" in cfg["script_url"]
    assert "secret" not in str(cfg).lower()


def test_turnstile_provider_config(captcha_on, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "turnstile")
    cfg = _fresh_client().get("/api/captcha/config").json()
    assert cfg["provider"] == "turnstile" and "challenges.cloudflare.com" in cfg["script_url"]


def test_tampered_and_expired_session_tokens_rejected(captcha_on, monkeypatch):
    from app.config import settings
    from app.services.captcha_service import captcha_service

    good = captcha_service.issue_session_token()
    assert captcha_service.is_valid_session_token(good)
    exp, sig = good.split(".")
    assert not captcha_service.is_valid_session_token(f"{int(exp) + 999}.{sig}")  # tampered expiry
    assert not captcha_service.is_valid_session_token("garbage")
    assert not captcha_service.is_valid_session_token(None)

    monkeypatch.setattr(settings, "CAPTCHA_SESSION_HOURS", -1)  # already expired
    assert not captcha_service.is_valid_session_token(captcha_service.issue_session_token())


def test_verify_uses_the_selected_provider_endpoint(captcha_on, monkeypatch):
    import asyncio
    from app.config import settings
    from app.services.captcha_service import captcha_service

    seen = {}

    class FakeResp:
        def json(self):
            return {"success": True}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, data=None):
            seen["url"], seen["data"] = url, data
            return FakeResp()

    monkeypatch.setattr("app.services.captcha_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "turnstile")
    assert asyncio.run(captcha_service.verify_token("tok", "1.2.3.4"))["success"] is True
    assert seen["url"] == "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    assert seen["data"]["secret"] == "secret-key-456" and seen["data"]["response"] == "tok"
