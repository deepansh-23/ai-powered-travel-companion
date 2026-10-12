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
    """Every test gets its own throw-away SQLite database through the same code path as
    PostgreSQL. Tests NEVER connect to the real Aiven database."""
    from app import db
    from app.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(settings, "DB_HOST", None)
    db.reset_for_tests()
    yield
    db.reset_for_tests()


@pytest.fixture(autouse=True)
def _logged_in_by_default():
    """Feature tests run as a logged-in user; test_auth.py turns this off."""
    from app.db_models import User
    from app.main import app
    from app.security import require_user

    fake = User(id="test-user-id", username="tester", username_lower="tester", password_hash="x")
    app.dependency_overrides[require_user] = lambda: fake
    yield
    app.dependency_overrides.pop(require_user, None)
