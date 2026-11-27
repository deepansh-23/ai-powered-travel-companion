"""Tests for the .env-configured recovery admin bootstrap, sync, login, and protection guards."""

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db, init_db
from app.db_models import AccountDeletionRequest, LoginAttempt, User
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service


@pytest.fixture(autouse=True)
def _real_auth_dependencies():
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    yield


@pytest.mark.asyncio
async def test_unset_env_admin_is_clean_noop():
    await init_db()
    await auth_service.ensure_env_admin()
    async for db in get_db():
        total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        assert total == 0
        break


@pytest.mark.asyncio
async def test_fresh_startup_creates_hashed_admin_and_is_idempotent(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "Recovery_Admin_01")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "Sup3r!Secret#Pass99")

    await init_db()
    with caplog.at_level(logging.INFO):
        await auth_service.ensure_env_admin()
        await auth_service.ensure_env_admin()  # repeated startup must be idempotent

    # Password must never appear in logs
    assert "Sup3r!Secret#Pass99" not in caplog.text

    async for db in get_db():
        users = (await db.execute(select(User))).scalars().all()
        assert len(users) == 1
        admin = users[0]
        assert admin.username == "Recovery_Admin_01"
        assert admin.username_lower == "recovery_admin_01"
        assert admin.is_admin is True
        assert admin.is_active is True
        assert admin.password_hash != "Sup3r!Secret#Pass99"
        assert admin.password_hash.startswith("$argon2")
        assert auth_service.verify_password(admin.password_hash, "Sup3r!Secret#Pass99") is True
        break


@pytest.mark.asyncio
async def test_recovery_sync_restores_password_role_active_and_clears_lockout(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "Recovery_Admin_02")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "EnvPass!2026#Safe")

    await init_db()
    await auth_service.ensure_env_admin()

    # Tamper with the DB row: change password, demote, deactivate, add lockout & deletion request
    async for db in get_db():
        user = (await db.execute(select(User).where(User.username_lower == "recovery_admin_02"))).scalar_one()
        user.password_hash = auth_service.hash_password("SomeOtherPassword!99")
        user.is_admin = False
        user.is_active = False
        db.add(LoginAttempt(username_lower="recovery_admin_02", ip="1.2.3.4", success=False))
        db.add(AccountDeletionRequest(user_id=user.id, reason="accidental", status="pending"))
        await db.commit()
        break

    # Run startup sync again — must restore everything cleanly
    await auth_service.ensure_env_admin()

    async for db in get_db():
        user = (await db.execute(select(User).where(User.username_lower == "recovery_admin_02"))).scalar_one()
        assert user.is_admin is True
        assert user.is_active is True
        assert auth_service.verify_password(user.password_hash, "EnvPass!2026#Safe") is True
        fail_count = (await db.execute(
            select(func.count()).select_from(LoginAttempt).where(LoginAttempt.username_lower == "recovery_admin_02")
        )).scalar_one()
        del_count = (await db.execute(
            select(func.count()).select_from(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id)
        )).scalar_one()
        assert fail_count == 0
        assert del_count == 0
        break


@pytest.mark.asyncio
async def test_env_admin_login_grants_admin_panel_access_without_leaking_secrets(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "Recovery_Admin_03")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "AdminLogin!2026#Key")

    await init_db()
    await auth_service.ensure_env_admin()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Standard /api/auth/login succeeds and marks user as admin
        r_login = await client.post("/api/auth/login", json={
            "username": "Recovery_Admin_03",
            "password": "AdminLogin!2026#Key",
        })
        assert r_login.status_code == 200, r_login.text
        assert r_login.json()["user"]["is_admin"] is True

        # 2. Step-up grants full Admin Panel API access
        r_stepup = await client.post("/api/admin/stepup", json={"password": "AdminLogin!2026#Key"})
        assert r_stepup.status_code == 200, r_stepup.text

        r_overview = await client.get("/api/admin/overview")
        assert r_overview.status_code == 200
        assert r_overview.json()["total_admins"] >= 1

        # 3. Settings & health endpoints never leak ADMIN_PASSWORD
        for endpoint in ("/api/admin/settings", "/api/settings/public", "/api/admin/system-health"):
            resp = await client.get(endpoint)
            assert resp.status_code == 200
            assert "AdminLogin!2026#Key" not in resp.text


@pytest.mark.asyncio
async def test_env_admin_is_protected_from_delete_disable_demote_and_reset(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_USERNAME", "Protected_Admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "Protected!Pass2026")

    await init_db()
    await auth_service.ensure_env_admin()

    # Create a second admin who tries to modify/delete the protected .env admin
    async for db in get_db():
        env_admin = (await db.execute(select(User).where(User.username_lower == "protected_admin"))).scalar_one()
        other_admin, _ = await auth_service.register(db, "Second_Admin", "SecondAdmin!2026")
        other_admin.is_admin = True
        await db.commit()
        other_token = await auth_service.create_session(db, other_admin)
        env_token = await auth_service.create_session(db, env_admin)
        env_id = env_admin.id
        other_id = other_admin.id
        break

    other_stepup, _ = issue_admin_stepup_token(other_id)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={settings.AUTH_COOKIE_NAME: other_token, ADMIN_STEPUP_COOKIE: other_stepup},
    ) as other_client:
        # Block deactivation
        r_disable = await other_client.patch(f"/api/admin/users/{env_id}", json={"is_active": False})
        assert r_disable.status_code == 403
        assert "recovery admin" in r_disable.json()["detail"].lower()

        # Block demotion
        r_demote = await other_client.patch(f"/api/admin/users/{env_id}", json={"is_admin": False})
        assert r_demote.status_code == 403
        assert "recovery admin" in r_demote.json()["detail"].lower()

        # Block deletion
        r_del = await other_client.delete(f"/api/admin/users/{env_id}")
        assert r_del.status_code == 403
        assert "recovery admin" in r_del.json()["detail"].lower()

        # Block password reset
        r_reset = await other_client.post(f"/api/admin/users/{env_id}/reset-password")
        assert r_reset.status_code == 403
        assert "recovery admin" in r_reset.json()["detail"].lower()

    # Block self-deletion and self deletion-request by the .env admin itself
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={settings.AUTH_COOKIE_NAME: env_token},
    ) as env_client:
        r_self_del = await env_client.post("/api/auth/delete-account", json={"password": "Protected!Pass2026"})
        assert r_self_del.status_code == 403
        assert "recovery admin" in r_self_del.json()["detail"].lower()

        r_self_req = await env_client.post("/api/auth/delete-request", json={"reason": "test"})
        assert r_self_req.status_code == 403
        assert "recovery admin" in r_self_req.json()["detail"].lower()


def test_app_lifespan_bootstraps_env_admin(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "ADMIN_USERNAME", "Lifespan_Admin")
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "Lifespan!Pass2026")

    with TestClient(app) as client:
        r_login = client.post("/api/auth/login", json={
            "username": "Lifespan_Admin",
            "password": "Lifespan!Pass2026",
        })
        assert r_login.status_code == 200, r_login.text
        assert r_login.json()["user"]["is_admin"] is True
        assert r_login.json()["user"]["username"] == "Lifespan_Admin"
