"""Posting a review needs a CAPTCHA tick (when CAPTCHA keys are configured), so scripts cannot spam reviews."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
MULTI = {"rating": 5, "comment": "Great planner", "services": ["Overall Website"]}
SINGLE = {"rating": 4, "comment": "Nice", "service_used": "Overall Website"}


@pytest.fixture
def captcha_on(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "site-key-123")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "secret-key-456")


def _verify(success):
    return patch("app.services.captcha_service.captcha_service.verify_token", new_callable=AsyncMock,
                 return_value={"success": success, "message": "CAPTCHA verification failed. Please tick the box again."})


def test_review_without_token_is_refused_when_captcha_is_on(captcha_on):
    for url, body in (("/api/feedback/multi", MULTI), ("/api/feedback", SINGLE)):
        res = client.post(url, json=body)
        assert res.status_code == 400 and "captcha" in res.json()["detail"].lower()
    assert client.get("/api/feedback").json() == []                 # nothing was saved


def test_review_with_rejected_token_is_refused(captcha_on):
    with _verify(False):
        res = client.post("/api/feedback/multi", json={**MULTI, "captcha_token": "stale-token"})
    assert res.status_code == 400 and "failed" in res.json()["detail"].lower()
    assert client.get("/api/feedback").json() == []


def test_review_with_valid_token_is_saved(captcha_on):
    with _verify(True) as v:
        res = client.post("/api/feedback/multi", json={**MULTI, "captcha_token": "good"})
        single = client.post("/api/feedback", json={**SINGLE, "captcha_token": "good-2"})
    assert res.status_code == 201 and single.status_code == 201
    assert v.await_count == 2                                         # verified on the server, once per post
    assert len(client.get("/api/feedback").json()) == 2


def test_no_captcha_needed_when_it_is_not_configured():
    assert client.post("/api/feedback/multi", json=MULTI).status_code == 201


def test_reviews_still_need_a_login(captcha_on):
    from app.security import require_user
    app.dependency_overrides.pop(require_user, None)
    with _verify(True):
        res = client.post("/api/feedback/multi", json={**MULTI, "captcha_token": "good"})
    assert res.status_code == 401


def test_provider_error_codes_are_explained_in_the_log(caplog):
    from app.services.captcha_service import CaptchaService
    with caplog.at_level("WARNING"):
        CaptchaService._log_failure(["invalid-input-secret", "timeout-or-duplicate"])
    text = caplog.text
    assert "invalid-input-secret" in text and "belong to the site key" in text and "already used" in text


def test_config_problems_are_named(monkeypatch):
    from app.config import settings
    from app.services.captcha_service import captcha_service
    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "6Labc")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", None)
    assert "SECRET_KEY is missing" in captcha_service.config_problem()
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "s")
    assert captcha_service.config_problem() is None
    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "0x4AAAA")
    assert "Turnstile" in captcha_service.config_problem()
