"""Admin Settings + Feedback & Diagnostics (Phase 6).

Covers: admin-only access, validated + persisted settings, confirmation of disruptive changes,
enforcement (registration, maintenance, reviews), feedback search/filter/paginate/status,
and PII redaction. Runs against the throw-away SQLite database from conftest.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from admin import service
from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db
from app.db_models import Feedback
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service


@pytest.fixture(autouse=True)
def _real_auth():
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    yield


async def _make_user(username: str, admin: bool):
    async for db in get_db():
        user, _ = await auth_service.register(db, username, "Password123#")
        if admin:
            user.is_admin = True
            await db.commit()
        token = await auth_service.create_session(db, user)
        return user.id, token


async def _admin_client():
    uid, token = await _make_user("adminuser", True)
    stepup, _ = issue_admin_stepup_token(uid)
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
        cookies={settings.AUTH_COOKIE_NAME: token, ADMIN_STEPUP_COOKIE: stepup},
    )


async def _add_feedback(n: int, **kw):
    async for db in get_db():
        for i in range(n):
            db.add(Feedback(
                id=f"rev_{uuid.uuid4().hex[:12]}", user_id=None, rating=kw.get("rating", 5),
                comment=kw.get("comment", f"comment {i}"), service_used=kw.get("service", "Itinerary Planner"),
                created_at=datetime.now(timezone.utc) - timedelta(minutes=i),
            ))
        await db.commit()
        break


# ───────────────────────────── access control ─────────────────────────────

@pytest.mark.asyncio
async def test_new_admin_endpoints_require_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in ("/api/admin/settings", "/api/admin/feedback", "/api/admin/diagnostics"):
            assert (await c.get(path)).status_code == 401
        assert (await c.put("/api/admin/settings", json={"maintenance_mode": False})).status_code == 401

    _, token = await _make_user("plainuser", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token}) as c:
        assert (await c.get("/api/admin/settings")).status_code == 403
        assert (await c.get("/api/admin/feedback")).status_code == 403


# ───────────────────────────── settings ─────────────────────────────

@pytest.mark.asyncio
async def test_settings_defaults_save_and_public_view():
    async with await _admin_client() as c:
        d = (await c.get("/api/admin/settings")).json()
        assert d["maintenance_mode"] is False and d["allow_registration"] is True
        assert d["guest_mode_enabled"] is True and d["allow_reviews"] is True

        # non-disruptive change saves without confirmation
        r = await c.put("/api/admin/settings", json={"public_notice_text": "  Hello   world  ", "public_notice_enabled": True})
        assert r.status_code == 200
        assert r.json()["public_notice_text"] == "Hello world"

        pub = (await c.get("/api/settings/public")).json()
        assert pub["public_notice_enabled"] is True and pub["public_notice_text"] == "Hello world"
        assert set(pub) == {"maintenance_mode", "public_notice_enabled", "public_notice_text",
                            "guest_mode_enabled", "allow_registration", "allow_reviews"}


@pytest.mark.asyncio
async def test_settings_validation():
    async with await _admin_client() as c:
        # banner on with no text
        r = await c.put("/api/admin/settings", json={"public_notice_enabled": True})
        assert r.status_code == 400
        # too long
        r = await c.put("/api/admin/settings", json={"public_notice_text": "x" * 301})
        assert r.status_code == 422
        # wrong type
        r = await c.put("/api/admin/settings", json={"allow_reviews": "maybe"})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_settings_cannot_be_stored():
    async for db in get_db():
        with pytest.raises(ValueError):
            await service.update_settings(db, {"GEMINI_API_KEY": "abc"})
        break


@pytest.mark.asyncio
async def test_disruptive_change_needs_confirmation():
    async with await _admin_client() as c:
        r = await c.put("/api/admin/settings", json={"maintenance_mode": True})
        assert r.status_code == 400 and "Confirmation" in r.json()["detail"]
        assert (await c.get("/api/admin/settings")).json()["maintenance_mode"] is False

        r = await c.put("/api/admin/settings", json={"maintenance_mode": True, "confirm_disruptive": True})
        assert r.status_code == 200 and r.json()["maintenance_mode"] is True

        # switching it back off is not disruptive
        r = await c.put("/api/admin/settings", json={"maintenance_mode": False})
        assert r.status_code == 200


# ───────────────────────────── enforcement ─────────────────────────────

@pytest.mark.asyncio
async def test_registration_and_guest_switches_are_enforced():
    async with await _admin_client() as c:
        r = await c.put("/api/admin/settings", json={
            "allow_registration": False, "guest_mode_enabled": False, "confirm_disruptive": True})
        assert r.status_code == 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        r = await anon.post("/api/auth/register", json={"username": "newperson", "password": "Password123#"})
        assert r.status_code == 403
        r = await anon.post("/api/auth/guest", json={})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_maintenance_blocks_public_api_but_not_admin():
    async with await _admin_client() as admin:
        r = await admin.put("/api/admin/settings", json={"maintenance_mode": True, "confirm_disruptive": True})
        assert r.status_code == 200

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
            assert (await anon.get("/api/places")).status_code == 503
            assert (await anon.get("/api/settings/public")).status_code == 200   # banner still loads
            assert (await anon.get("/api/health")).status_code != 503

        assert (await admin.get("/api/admin/settings")).status_code == 200
        assert (await admin.get("/api/places")).status_code != 503              # admin bypass


@pytest.mark.asyncio
async def test_reviews_switch_is_enforced():
    async with await _admin_client() as admin:
        await admin.put("/api/admin/settings", json={"allow_reviews": False, "confirm_disruptive": True})
    _, token = await _make_user("reviewer", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token}) as c:
        r = await c.post("/api/feedback", json={"rating": 5, "comment": "great trip planner"})
        assert r.status_code == 403


# ───────────────────────────── feedback ─────────────────────────────

@pytest.mark.asyncio
async def test_feedback_list_filter_paginate_and_status():
    await _add_feedback(25)
    await _add_feedback(1, rating=1, comment="Broken map", service="Area Guide")
    async with await _admin_client() as c:
        d = (await c.get("/api/admin/feedback")).json()
        assert d["total"] == 26 and d["pages"] == 2 and len(d["items"]) == 20
        assert d["summary"]["pending"] == 26 and "user_id" not in d["items"][0]

        assert (await c.get("/api/admin/feedback?page=2")).json()["items"].__len__() == 6
        assert (await c.get("/api/admin/feedback?search=broken")).json()["total"] == 1
        assert (await c.get("/api/admin/feedback?service_used=Area Guide")).json()["total"] == 1
        assert (await c.get("/api/admin/feedback?rating=1")).json()["total"] == 1

        fid = (await c.get("/api/admin/feedback?search=broken")).json()["items"][0]["id"]
        r = await c.patch(f"/api/admin/feedback/{fid}", json={"status": "resolved", "admin_notes": "fixed in v2"})
        assert r.status_code == 200 and r.json()["status"] == "resolved"
        assert (await c.get("/api/admin/feedback?status=resolved")).json()["total"] == 1
        assert (await c.get("/api/admin/feedback")).json()["summary"]["resolved"] == 1

        assert (await c.patch(f"/api/admin/feedback/{fid}", json={"status": "bogus"})).status_code == 422
        assert (await c.patch("/api/admin/feedback/nope", json={"status": "reviewed"})).status_code == 404


@pytest.mark.asyncio
async def test_feedback_redacts_personal_data():
    await _add_feedback(1, comment="mail me at jane.doe@example.com or call +91 98765 43210 token abcdefghijklmnopqrstuvwxyz0123456789")
    async with await _admin_client() as c:
        text = (await c.get("/api/admin/feedback")).json()["items"][0]["comment"]
        assert "example.com" not in text and "98765" not in text and "abcdefghijklmnop" not in text
        assert "[email hidden]" in text and "[phone hidden]" in text and "[secret hidden]" in text


# ───────────────────────────── diagnostics ─────────────────────────────

@pytest.mark.asyncio
async def test_diagnostics_are_sanitized_and_bounded():
    from admin.monitoring import metrics_tracker
    metrics_tracker.record("POST", "/api/itinerary", 500, 12.0, client_ip="203.0.113.77", exc_type="KeyError")
    async with await _admin_client() as c:
        d = (await c.get("/api/admin/diagnostics?level=5xx&limit=5")).json()
        assert d["items"] and d["items"][0]["client_ip_masked"] == "203.0.113.xxx"
        assert "KeyError" in d["items"][0]["error_summary"]
        assert "203.0.113.77" not in str(d)
        assert (await c.get("/api/admin/diagnostics?limit=500")).status_code == 422
    assert metrics_tracker.diagnostics.maxlen == 300


# ───────────────────────────── stay signed in ─────────────────────────────

@pytest.mark.asyncio
async def test_stepup_is_renewed_while_admin_is_active():
    from admin import permissions
    uid, token = await _make_user("sliding", True)
    # a token that is valid but close to expiring
    old, _ = permissions.issue_admin_stepup_token(uid)
    parts = old.split(".")
    soon = int(__import__("time").time()) + 60
    import hmac, hashlib
    payload = f"{uid}.{soon}.{parts[2]}"
    sig = hmac.new(permissions._stepup_secret(), payload.encode(), hashlib.sha256).hexdigest()
    near_expiry = f"{payload}.{sig}"
    assert permissions.is_valid_admin_stepup(near_expiry, uid)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token, ADMIN_STEPUP_COOKIE: near_expiry}) as c:
        r = await c.get("/api/admin/settings")
        assert r.status_code == 200
        header = r.headers.get("set-cookie", "")
        assert ADMIN_STEPUP_COOKIE in header                              # fresh cookie issued
        fresh = header.split(f"{ADMIN_STEPUP_COOKIE}=")[1].split(";")[0]
        assert permissions.stepup_seconds_left(fresh) > 25 * 60


def test_signing_secret_is_stable_without_auth_secret():
    from app.security import derive_fallback_secret
    assert derive_fallback_secret("admin-stepup") == derive_fallback_secret("admin-stepup")


@pytest.mark.asyncio
async def test_maintenance_also_pauses_signup_and_guest():
    async with await _admin_client() as admin:
        await admin.put("/api/admin/settings", json={"maintenance_mode": True, "confirm_disruptive": True})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
            assert (await anon.post("/api/auth/register", json={"username": "x" * 5, "password": "Password123#"})).status_code == 503
            assert (await anon.post("/api/auth/guest", json={})).status_code == 503
            assert (await anon.get("/api/auth/me")).status_code == 200   # login page + banner still work
