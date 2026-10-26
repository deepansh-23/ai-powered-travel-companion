"""Admin analytics, usage tracking, account controls, password reset and deletion requests."""

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db
from app.db_models import AccountDeletionRequest, ActivityDaily, AuthSession, User
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service
from app.services.activity_service import ActivityTracker, activity_tracker


@pytest.fixture(autouse=True)
def _real_auth():
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    activity_tracker._buffer.clear()
    activity_tracker._session_cache.clear()
    yield


async def _make_user(username, admin=False):
    async for db in get_db():
        user, _ = await auth_service.register(db, username, "Password123#")
        if admin:
            user.is_admin = True
            await db.commit()
        token = await auth_service.create_session(db, user)
        return user.id, token


async def _admin():
    uid, token = await _make_user("adminuser", True)
    stepup, _ = issue_admin_stepup_token(uid)
    def make():
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token, ADMIN_STEPUP_COOKIE: stepup})
    return uid, make


async def _seed_activity(rows):
    async for db in get_db():
        for day, actor, kind, feature, n in rows:
            db.add(ActivityDaily(day=day, actor_id=actor, kind=kind, feature=feature, count=n))
        await db.commit()
        break


# ----------------------------------------------------------------- tracking
@pytest.mark.asyncio
async def test_tracker_counts_visits_and_feature_use_and_flushes_to_the_database():
    uid, token = await _make_user("walker")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token}) as c:
        assert (await c.get("/api/auth/me")).status_code == 200
        await c.post("/api/places/search", json={"location": "Goa"})    # may fail upstream; only successes are counted
    await activity_tracker.flush()
    async for db in get_db():
        from sqlalchemy import select
        rows = (await db.execute(select(ActivityDaily))).scalars().all()
        assert any(r.actor_id == uid and r.feature == "visit" and r.kind == "registered" and r.count == 1 for r in rows)
        break


@pytest.mark.asyncio
async def test_guest_visits_are_counted_as_guests_without_any_personal_data():
    from app.security import issue_guest_token
    token = issue_guest_token()[0] if isinstance(issue_guest_token(), tuple) else issue_guest_token()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.GUEST_COOKIE_NAME: token}) as c:
        await c.get("/api/auth/me")
    await activity_tracker.flush()
    async for db in get_db():
        from sqlalchemy import select
        rows = (await db.execute(select(ActivityDaily))).scalars().all()
        assert rows and all(r.kind == "guest" and r.actor_id.startswith("g") for r in rows)
        break


def test_buffer_is_bounded():
    t = ActivityTracker()
    for i in range(25000):
        t.record(f"u{i}", "registered", "visit")
    assert len(t._buffer) <= 20000


# ----------------------------------------------------------------- analytics numbers
@pytest.mark.asyncio
async def test_analytics_numbers_ranges_and_features():
    uid, admin = await _admin()
    today = datetime.now(timezone.utc).date()
    d = lambda n: today - timedelta(days=n)
    await _seed_activity([
        (d(0), "u1", "registered", "visit", 3), (d(0), "u1", "registered", "itinerary", 2), (d(0), "g1", "guest", "visit", 1),
        (d(0), "g1", "guest", "cafes", 4), (d(3), "u2", "registered", "visit", 1), (d(3), "u2", "registered", "area", 5),
        (d(20), "u1", "registered", "visit", 1), (d(40), "u9", "registered", "visit", 1),
    ])
    async with admin() as c:
        r = (await c.get("/api/admin/analytics?days=7")).json()
        s = r["summary"]
        assert (s["dau"], s["dau_registered"], s["dau_guest"]) == (2, 1, 1)
        assert s["wau"] == 3 and s["mau"] == 3                       # u1 + g1 + u2 within 30 days; u9 (40 days ago) not
        assert r["range_totals"]["active_registered"] == 2 and r["range_totals"]["active_guest"] == 1
        top = {f["key"]: f for f in r["features"]}
        assert top["area"]["registered"] == 5 and top["cafes"]["guest"] == 4 and top["itinerary"]["registered"] == 2
        assert r["features"][0]["key"] == "area"                      # sorted by use
        assert len(r["series"]) == 7 and r["series"][-1]["active_guest"] == 1

        weekly = (await c.get("/api/admin/analytics?days=30&interval=week")).json()
        assert weekly["interval"] == "week" and 4 <= len(weekly["series"]) <= 6
        monthly = (await c.get("/api/admin/analytics?days=90&interval=month")).json()
        assert monthly["interval"] == "month" and 3 <= len(monthly["series"]) <= 5


@pytest.mark.asyncio
async def test_analytics_new_vs_returning_and_registrations_from_accounts():
    uid, admin = await _admin()
    old_id, _ = await _make_user("veteran")
    async for db in get_db():                                         # the veteran registered 60 days ago
        u = await db.get(User, old_id)
        u.created_at = datetime.now(timezone.utc) - timedelta(days=60)
        await db.commit()
        break
    today = datetime.now(timezone.utc).date()
    await _seed_activity([(today, old_id, "registered", "visit", 1), (today, uid, "registered", "visit", 1)])
    async with admin() as c:
        r = (await c.get("/api/admin/analytics?days=7")).json()
        assert r["range_totals"]["new_registrations"] == 1            # only the admin account was created in the range
        assert r["range_totals"]["returning_users"] == 1 and r["range_totals"]["new_active_users"] == 1
        assert r["series"][-1]["returning_users"] == 1


@pytest.mark.asyncio
async def test_analytics_validates_dates_and_needs_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.get("/api/admin/analytics")).status_code == 401
    _, admin = await _admin()
    async with admin() as c:
        assert (await c.get("/api/admin/analytics?start=2026-02-01&end=2026-01-01")).status_code == 400
        assert (await c.get("/api/admin/analytics?start=nope&end=2026-01-01")).status_code == 400
        assert (await c.get("/api/admin/analytics?start=2020-01-01&end=2026-01-01")).status_code == 400   # over a year
        assert (await c.get("/api/admin/analytics?interval=hour")).status_code == 422


# ----------------------------------------------------------------- accounts
@pytest.mark.asyncio
async def test_user_list_has_last_activity_filters_and_sorting():
    admin_id, admin = await _admin()
    a_id, _ = await _make_user("alice")
    b_id, _ = await _make_user("bruno")
    async for db in get_db():
        await db.execute(__import__("sqlalchemy").update(User).where(User.id == b_id).values(is_active=False))
        await db.commit()
        break
    async with admin() as c:
        d = (await c.get("/api/admin/users")).json()
        assert d["total"] == 3 and all("last_active_at" in u and "deletion_requested" in u for u in d["users"])
        assert d["users"][0]["last_active_at"] is not None                      # sessions exist for these users
        assert [u["username"] for u in (await c.get("/api/admin/users?status=suspended")).json()["users"]] == ["bruno"]
        assert (await c.get("/api/admin/users?status=active")).json()["total"] == 2
        assert [u["username"] for u in (await c.get("/api/admin/users?sort=username")).json()["users"]] == ["adminuser", "alice", "bruno"]
        assert (await c.get("/api/admin/users?sort=last_active")).status_code == 200
        assert (await c.get("/api/admin/users?status=bogus")).status_code == 422


@pytest.mark.asyncio
async def test_admin_can_reset_a_password_once_with_strict_rules():
    admin_id, admin = await _admin()
    uid, token = await _make_user("forgetful")
    other_admin, _ = await _make_user("coadmin", True)
    async with admin() as c:
        r = await c.post(f"/api/admin/users/{uid}/reset-password")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        temp = r.json()["temporary_password"]
        assert len(temp) >= 12
        # the old session is gone, the old password no longer works and the new one does
        async for db in get_db():
            from sqlalchemy import select
            assert (await db.execute(select(AuthSession).where(AuthSession.user_id == uid))).first() is None
            with pytest.raises(auth_service.AuthError):
                await auth_service.authenticate(db, "forgetful", "Password123#", "1.1.1.1")
            assert (await auth_service.authenticate(db, "forgetful", temp, "1.1.1.1")).id == uid
            break
        assert (await c.post(f"/api/admin/users/{admin_id}/reset-password")).status_code == 400        # not your own
        assert (await c.post(f"/api/admin/users/{other_admin}/reset-password")).status_code == 400      # not another admin
        assert (await c.post("/api/admin/users/nope/reset-password")).status_code == 404
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={settings.AUTH_COOKIE_NAME: token}) as plain:
        assert (await plain.post(f"/api/admin/users/{uid}/reset-password")).status_code in (401, 403)


@pytest.mark.asyncio
async def test_deletion_request_flow_user_asks_admin_decides():
    admin_id, admin = await _admin()
    uid, token = await _make_user("leaver")
    keep_id, keep_token = await _make_user("stayer")
    user = lambda: AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={settings.AUTH_COOKIE_NAME: token})
    async with user() as u:
        assert (await u.get("/api/auth/delete-request")).json()["pending"] is False
        assert (await u.post("/api/auth/delete-request", json={"reason": "  Not   travelling  anymore "})).status_code == 200
        assert (await u.get("/api/auth/delete-request")).json()["pending"] is True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.post("/api/auth/delete-request", json={})).status_code == 401
    async with admin() as c:
        reqs = (await c.get("/api/admin/deletion-requests")).json()
        assert reqs["total"] == 1 and reqs["requests"][0]["username"] == "leaver" and reqs["requests"][0]["reason"] == "Not travelling anymore"
        flagged = (await c.get("/api/admin/users?status=deletion_requested")).json()
        assert [x["username"] for x in flagged["users"]] == ["leaver"] and flagged["users"][0]["deletion_reason"]
        # dismissing keeps the account; the user can ask again
        rid = reqs["requests"][0]["id"]
        assert (await c.post(f"/api/admin/deletion-requests/{rid}/dismiss")).status_code == 204
        assert (await c.get("/api/admin/deletion-requests")).json()["total"] == 0
    async with user() as u:
        await u.post("/api/auth/delete-request", json={})
    async with admin() as c:
        rid = (await c.get("/api/admin/deletion-requests")).json()["requests"][0]["id"]
        assert (await c.post(f"/api/admin/deletion-requests/{rid}/approve")).status_code == 204
        assert (await c.get("/api/admin/deletion-requests")).json()["total"] == 0
        assert (await c.get(f"/api/admin/users/{uid}")).status_code == 404            # account is gone
        assert (await c.get(f"/api/admin/users/{keep_id}")).status_code == 200
        assert (await c.post("/api/admin/deletion-requests/nope/approve")).status_code == 404


@pytest.mark.asyncio
async def test_user_can_withdraw_a_deletion_request():
    uid, token = await _make_user("hesitant")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={settings.AUTH_COOKIE_NAME: token}) as u:
        await u.post("/api/auth/delete-request", json={"reason": "x"})
        assert (await u.delete("/api/auth/delete-request")).status_code == 200
        assert (await u.get("/api/auth/delete-request")).json()["pending"] is False
