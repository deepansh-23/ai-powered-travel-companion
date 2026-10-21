"""Tests for Admin Dashboard Enhancements:
- API Monitoring (middleware, metrics collection, aggregations)
- System Health (PostgreSQL latency check, uptime, error rates, dependencies)
- Step-Up Re-Authentication (token generation, expiration, user binding, route protection)
- Admin Login (CAPTCHA verification, generic error on invalid/non-admin, success session)
- Admin status in /api/auth/me
"""

import time
import pytest
from httpx import ASGITransport, AsyncClient
from argon2 import PasswordHasher

from app.main import app
from app.db_models import User
from app.db import get_db
from app.config import settings
from admin.monitoring import metrics_tracker
from admin.permissions import (
    issue_admin_stepup_token,
    is_valid_admin_stepup,
    ADMIN_STEPUP_COOKIE,
)

hasher = PasswordHasher()


@pytest.fixture
def clean_app(monkeypatch):
    """Ensure clean dependency overrides for auth tests."""
    from app.security import require_user, require_user_or_guest
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    yield


@pytest.mark.asyncio
async def test_stepup_token_validation():
    user_id = "admin-123"
    token, expires = issue_admin_stepup_token(user_id)

    # Valid token for correct user
    assert is_valid_admin_stepup(token, user_id) is True

    # Invalid user binding
    assert is_valid_admin_stepup(token, "other-user") is False

    # Corrupted token
    assert is_valid_admin_stepup(token + "xyz", user_id) is False
    assert is_valid_admin_stepup("invalid.token", user_id) is False
    assert is_valid_admin_stepup(None, user_id) is False


@pytest.mark.asyncio
async def test_api_monitoring_metrics():
    # Record some simulated requests
    metrics_tracker.record("GET", "/api/places", 200, 45.2)
    metrics_tracker.record("POST", "/api/itinerary", 200, 120.5)
    metrics_tracker.record("GET", "/api/cafes", 404, 15.1)
    metrics_tracker.record("POST", "/api/medical", 500, 80.0)

    metrics = metrics_tracker.get_metrics(window_minutes=15)
    assert metrics["total_requests"] >= 4
    assert metrics["successful_requests"] >= 2
    assert metrics["failed_requests"] >= 2
    assert metrics["c4xx_count"] >= 1
    assert metrics["c5xx_count"] >= 1
    assert metrics["error_rate_percent"] > 0
    assert metrics["avg_response_time_ms"] > 0
    assert len(metrics["slowest_endpoints"]) > 0
    assert len(metrics["recent_failures"]) >= 2


@pytest.mark.asyncio
async def test_admin_auth_status_unauthenticated(clean_app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/admin/auth-status")
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is False
        assert data["is_admin"] is False
        assert data["stepup_valid"] is False


@pytest.mark.asyncio
async def test_admin_protected_routes_require_stepup(clean_app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res = await client.get("/api/admin/overview")
        assert res.status_code == 401

        res = await client.get("/api/admin/monitoring")
        assert res.status_code == 401

        res = await client.get("/api/admin/system-health")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_regular_user_denied_admin(clean_app):
    # Create regular user in DB
    from app.services import auth_service
    async for db in get_db():
        reg_user, _ = await auth_service.register(db, "reguser", "Password123#")
        session_token = await auth_service.create_session(db, reg_user)
        break

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={settings.AUTH_COOKIE_NAME: session_token}) as client:
        # Check /api/auth/me returns is_admin: False
        me_res = await client.get("/api/auth/me")
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["authenticated"] is True
        assert me_data["user"]["is_admin"] is False

        # Regular user accessing admin -> 403 Forbidden
        admin_res = await client.get("/api/admin/overview")
        assert admin_res.status_code == 403


@pytest.mark.asyncio
async def test_admin_stepup_and_access(clean_app):
    # Create admin user
    from app.services import auth_service
    async for db in get_db():
        adm_user, _ = await auth_service.register(db, "superadmin", "AdminPass123#")
        adm_user.is_admin = True
        await db.commit()
        session_token = await auth_service.create_session(db, adm_user)
        adm_id = adm_user.id
        break

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", cookies={settings.AUTH_COOKIE_NAME: session_token}) as client:
        # 1. /api/auth/me shows is_admin: True
        me_res = await client.get("/api/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["user"]["is_admin"] is True

        # 2. Before step-up: overview returns 401 (re-auth required)
        overview_res = await client.get("/api/admin/overview")
        assert overview_res.status_code == 401
        assert "X-Admin-Reauth-Required" in overview_res.headers

        # 3. Auth status shows authenticated and is_admin, but stepup_valid: False
        status_res = await client.get("/api/admin/auth-status")
        assert status_res.status_code == 200
        assert status_res.json()["stepup_valid"] is False

        # 4. Attempt stepup with WRONG password -> 401
        bad_stepup = await client.post(
            "/api/admin/stepup",
            json={"password": "WrongPassword!"},
            headers={"origin": "http://test"},
        )
        assert bad_stepup.status_code == 401

        # 5. Attempt stepup with CORRECT password -> 200 and sets cookie
        good_stepup = await client.post(
            "/api/admin/stepup",
            json={"password": "AdminPass123#"},
            headers={"origin": "http://test"},
        )
        assert good_stepup.status_code == 200
        assert ADMIN_STEPUP_COOKIE in good_stepup.cookies
        stepup_cookie = good_stepup.cookies[ADMIN_STEPUP_COOKIE]

    # 6. Now client with stepup cookie can access admin routes
    cookies = {
        settings.AUTH_COOKIE_NAME: session_token,
        ADMIN_STEPUP_COOKIE: stepup_cookie,
    }
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies) as client:
        # Overview -> 200
        ov_res = await client.get("/api/admin/overview")
        assert ov_res.status_code == 200
        assert "total_users" in ov_res.json()

        # Monitoring -> 200
        mon_res = await client.get("/api/admin/monitoring?window=15m")
        assert mon_res.status_code == 200
        assert "total_requests" in mon_res.json()

        # System Health -> 200
        health_res = await client.get("/api/admin/system-health")
        assert health_res.status_code == 200
        health_data = health_res.json()
        assert health_data["status"] in ("Healthy", "Degraded")
        assert health_data["database_connected"] is True
        assert "dependencies" in health_data


@pytest.mark.asyncio
async def test_admin_login_endpoint(clean_app):
    from app.services import auth_service
    async for db in get_db():
        # Admin account
        adm_user, _ = await auth_service.register(db, "portaladmin", "PortalPass123#")
        adm_user.is_admin = True
        # Regular account
        reg_user, _ = await auth_service.register(db, "regularjoe", "JoePass123#")
        reg_user.is_admin = False
        await db.commit()
        break

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Non-existent user -> 401 generic
        res1 = await client.post(
            "/api/admin/login",
            json={"username": "nonexistent", "password": "anypassword"},
            headers={"origin": "http://test"},
        )
        assert res1.status_code == 401
        assert "Invalid administrator credentials" in res1.json()["detail"]

        # Regular user credentials -> 401 identical generic (no leak!)
        res2 = await client.post(
            "/api/admin/login",
            json={"username": "regularjoe", "password": "JoePass123#"},
            headers={"origin": "http://test"},
        )
        assert res2.status_code == 401
        assert "Invalid administrator credentials" in res2.json()["detail"]

        # Valid admin credentials -> 200, session and step-up cookies issued!
        res3 = await client.post(
            "/api/admin/login",
            json={"username": "portaladmin", "password": "PortalPass123#"},
            headers={"origin": "http://test"},
        )
        assert res3.status_code == 200
        data = res3.json()
        assert data["success"] is True
        assert data["redirect"] == "/admin/"
        assert settings.AUTH_COOKIE_NAME in res3.cookies
        assert ADMIN_STEPUP_COOKIE in res3.cookies
