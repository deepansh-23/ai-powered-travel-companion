"""pytest configuration — forces MOCK_MODE=true so tests run without API keys.

Tests are designed to run against the bundled mock dataset.
Live (MOCK_MODE=false) integration tests require real Geoapify and Gemini API keys
and should be run separately against a real backend environment.
"""

import os

# Force mock mode for all tests so no external API calls are made
os.environ["MOCK_MODE"] = "true"

import pytest


@pytest.fixture(autouse=True)
def _captcha_off_by_default(monkeypatch):
    """Tests must not depend on whatever CAPTCHA keys are in the developer's .env.
    CAPTCHA tests turn it on explicitly with their own monkeypatch."""
    from app.config import settings

    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", None)
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", None)
    monkeypatch.setattr(settings, "CAPTCHA_PROVIDER", "recaptcha")


@pytest.fixture(autouse=True)
def _isolated_database(monkeypatch, tmp_path):
    """Tests write reviews/history to a throw-away database, never to the real
    data/app_storage.db (otherwise test reviews would appear on the live site)."""
    from app.services.storage_service import storage_service

    monkeypatch.setattr(storage_service, "db_path", tmp_path / "test_storage.db")
    storage_service._init_db()
