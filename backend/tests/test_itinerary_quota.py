"""Monthly itinerary limit: admin setting, enforcement for normal accounts, no limit for admins, refunds, display."""

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from admin import service as admin_service
from app.db import session_scope
from app.db_models import ItineraryUsage, User
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import itinerary_quota_service as quota
from sqlalchemy import select

PAYLOAD = {"destination": "Delhi", "duration_days": 2, "budget_per_person_per_day": 4000.0, "travelers_count": 2, "interests": ["food"]}


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _set_limit(n):
    async with session_scope() as db:
        await admin_service.update_settings(db, {"itinerary_monthly_limit": n})


def _login_as(user_id="quota-user", admin=False):
    fake = User(id=user_id, username=user_id, username_lower=user_id, password_hash="x", is_admin=admin)
    app.dependency_overrides[require_user] = lambda: fake
    app.dependency_overrides[require_user_or_guest] = lambda: fake
    return fake


async def _used(user_id):
    async with session_scope() as db:
        return (await db.execute(select(ItineraryUsage.count).where(
            ItineraryUsage.user_id == user_id, ItineraryUsage.month == quota.month_key()))).scalar_one_or_none()


@pytest.mark.asyncio
async def test_no_limit_by_default_and_never_blocks():
    _login_as()
    async with _client() as c:
        for _ in range(3):
            assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        q = (await c.get("/api/itinerary/quota")).json()
    assert q["unlimited"] is True and q["limit"] == 0 and q["remaining"] is None


@pytest.mark.asyncio
async def test_limit_of_two_allows_two_then_blocks_with_a_clear_message():
    await _set_limit(2)
    _login_as()
    async with _client() as c:
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        assert (await c.get("/api/itinerary/quota")).json()["remaining"] == 1
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        blocked = await c.post("/api/itinerary/generate", json=PAYLOAD)
        assert blocked.status_code == 429
        assert "all 2 itineraries" in blocked.json()["detail"] and "resets on" in blocked.json()["detail"]
        q = (await c.get("/api/itinerary/quota")).json()
    assert q["limit"] == 2 and q["used"] == 2 and q["remaining"] == 0 and q["unlimited"] is False
    assert await _used("quota-user") == 2          # the blocked attempt was not counted


@pytest.mark.asyncio
async def test_limit_is_per_account():
    await _set_limit(1)
    async with _client() as c:
        _login_as("alice")
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 429
        _login_as("bob")
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200


@pytest.mark.asyncio
async def test_admin_account_is_never_limited_or_counted():
    await _set_limit(1)
    _login_as("boss", admin=True)
    async with _client() as c:
        for _ in range(3):
            assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        q = (await c.get("/api/itinerary/quota")).json()
    assert q["is_admin"] is True and q["unlimited"] is True
    assert await _used("boss") is None


@pytest.mark.asyncio
async def test_failed_generation_gives_the_slot_back(monkeypatch):
    from app.routes import itinerary as route

    await _set_limit(1)
    _login_as()

    async def boom(_req):
        raise RuntimeError("the AI service is down")
    monkeypatch.setattr(route, "_generate_itinerary", boom)
    async with _client() as c:
        with pytest.raises(RuntimeError):
            await c.post("/api/itinerary/generate", json=PAYLOAD)
    assert await _used("quota-user") == 0           # nothing was used up by the failure


@pytest.mark.asyncio
async def test_count_restarts_in_a_new_month(monkeypatch):
    await _set_limit(1)
    _login_as()
    async with _client() as c:
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 429
        real = quota._now
        monkeypatch.setattr(quota, "_now", lambda: datetime(2099, 1, 15, tzinfo=timezone.utc))
        assert (await c.post("/api/itinerary/generate", json=PAYLOAD)).status_code == 200      # a new month
        monkeypatch.setattr(quota, "_now", real)


def test_month_helpers():
    assert quota.month_key(datetime(2026, 12, 31, tzinfo=timezone.utc)) == "2026-12"
    assert quota.next_reset(datetime(2026, 12, 31, tzinfo=timezone.utc)).date().isoformat() == "2027-01-01"
    assert quota.next_reset(datetime(2026, 3, 5, tzinfo=timezone.utc)).date().isoformat() == "2026-04-01"


@pytest.mark.asyncio
async def test_guest_sees_no_allowance():
    app.dependency_overrides[require_user_or_guest] = lambda: None
    async with _client() as c:
        assert (await c.get("/api/itinerary/quota")).json()["guest"] is True


# ---------------------------------------------------------------- the admin setting itself
@pytest.mark.asyncio
async def test_setting_validation():
    async with session_scope() as db:
        assert (await admin_service.get_settings(db))["itinerary_monthly_limit"] == 0
        assert (await admin_service.update_settings(db, {"itinerary_monthly_limit": 5}))["itinerary_monthly_limit"] == 5
        for bad in (-1, 1001, True, "3", 2.5):
            with pytest.raises(ValueError):
                await admin_service.update_settings(db, {"itinerary_monthly_limit": bad})
        assert (await admin_service.update_settings(db, {"itinerary_monthly_limit": 0}))["itinerary_monthly_limit"] == 0
