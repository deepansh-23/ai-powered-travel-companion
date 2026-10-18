"""Accounts: register / login / logout / lockout / recovery, plus per-user History and Reviews.

Runs against a throw-away SQLite database through the same SQLAlchemy code as PostgreSQL.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.main import app
from app.security import require_user, require_user_or_guest


@pytest.fixture(autouse=True)
def _real_login_required():
    """Undo the 'always logged in' default from conftest: these tests use real sessions."""
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:  # runs start-up: creates the tables
        yield c


def _register(c, username="alice", password="correct horse 42"):
    return c.post("/api/auth/register", json={"username": username, "password": password})


# ------------------------------------------------------------------ registration
def test_register_logs_in_and_shows_recovery_code_once(client):
    r = _register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["username"] == "alice" and "password" not in str(body).lower()
    code = body["recovery_code"]
    assert len(code.replace("-", "")) == 16 and code.count("-") == 3

    cookie = r.headers["set-cookie"]
    assert settings.AUTH_COOKIE_NAME in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie

    me = client.get("/api/auth/me").json()
    assert me == {"authenticated": True, "user": me["user"], "accounts_available": True, "guest": False}
    assert me["user"]["username"] == "alice"


@pytest.mark.parametrize("username,password,fragment", [
    ("ab", "correct horse 42", "3 to 30"),
    ("bad name!", "correct horse 42", "letters, numbers"),
    ("alice", "short", "at least 8"),
    ("alice", "password123", "too common"),
    ("alice", "alice-is-me-123", "must not contain your username"),
])
def test_registration_validation(client, username, password, fragment):
    r = _register(client, username, password)
    assert r.status_code == 422 and fragment in r.json()["detail"]


def test_username_is_unique_case_insensitively(client):
    assert _register(client, "Alice").status_code == 201
    client.post("/api/auth/logout")
    r = _register(client, "aLiCe", "another secret 99")
    assert r.status_code == 409 and "taken" in r.json()["detail"]


def test_passwords_are_stored_as_argon2_hashes_only(client):
    import asyncio
    from sqlalchemy import select
    from app.db import get_engine
    from app.db_models import User

    _register(client, "bob", "my own passphrase 7")

    async def read():
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(get_engine()) as s:
            return (await s.execute(select(User).where(User.username_lower == "bob"))).scalar_one()

    user = asyncio.run(read())
    assert user.password_hash.startswith("$argon2") and "passphrase" not in user.password_hash
    assert user.recovery_code_hash.startswith("$argon2")


# ------------------------------------------------------------------ login / logout
def test_login_logout_flow(client):
    _register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["authenticated"] is False

    assert client.post("/api/auth/login", json={"username": "ALICE", "password": "correct horse 42"}).status_code == 200
    assert client.get("/api/auth/me").json()["user"]["username"] == "alice"

    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_wrong_password_and_unknown_user_look_identical(client):
    _register(client)
    client.post("/api/auth/logout")
    a = client.post("/api/auth/login", json={"username": "alice", "password": "wrong password!"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong password!"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"] == "Incorrect username or password."


def test_lockout_after_repeated_failures_then_correct_password_still_blocked(client):
    _register(client)
    client.post("/api/auth/logout")
    for _ in range(settings.AUTH_MAX_FAILED_ATTEMPTS):
        assert client.post("/api/auth/login", json={"username": "alice", "password": "nope nope nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "alice", "password": "correct horse 42"})
    assert r.status_code == 429 and "minute" in r.json()["detail"]


def test_logout_invalidates_the_old_session_cookie(client):
    r = _register(client)
    token = client.cookies.get(settings.AUTH_COOKIE_NAME)
    client.post("/api/auth/logout")
    client.cookies.set(settings.AUTH_COOKIE_NAME, token)  # replay the stolen/old cookie
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_expired_session_is_rejected(client):
    import asyncio
    from datetime import timedelta
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db import get_engine
    from app.db_models import AuthSession, utcnow

    _register(client)

    async def expire():
        async with AsyncSession(get_engine()) as s:
            await s.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
            await s.commit()

    asyncio.run(expire())
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_garbage_cookie_is_rejected(client):
    client.cookies.set(settings.AUTH_COOKIE_NAME, "not-a-real-token")
    assert client.get("/api/auth/me").json()["authenticated"] is False


# ------------------------------------------------------------------ recovery / change password
def test_recovery_code_resets_password_once_and_rotates(client):
    code = _register(client).json()["recovery_code"]
    client.post("/api/auth/logout")

    r = client.post("/api/auth/recover", json={
        "username": "alice", "recovery_code": code.lower(), "new_password": "brand new pass 55"})
    assert r.status_code == 200
    new_code = r.json()["recovery_code"]
    assert new_code and new_code != code

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "alice", "password": "correct horse 42"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "alice", "password": "brand new pass 55"}).status_code == 200

    # the old code no longer works
    client.post("/api/auth/logout")
    bad = client.post("/api/auth/recover", json={"username": "alice", "recovery_code": code, "new_password": "yet another 66"})
    assert bad.status_code == 401


def test_change_password(client):
    _register(client)
    assert client.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "fresh secret 12"}).status_code == 401
    assert client.post("/api/auth/change-password", json={"current_password": "correct horse 42", "new_password": "fresh secret 12"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "alice", "password": "fresh secret 12"}).status_code == 200


# ------------------------------------------------------------------ protection
def test_cross_site_origin_is_blocked_for_login(client):
    r = client.post("/api/auth/login", json={"username": "a", "password": "b"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_captcha_is_required_on_register_and_login_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "site")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "secret")

    assert _register(client).status_code == 400  # no token

    with patch("app.services.captcha_service.captcha_service.verify_token", new_callable=AsyncMock,
               return_value={"success": False, "message": "CAPTCHA verification failed."}):
        r = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse 42", "captcha_token": "bad"})
    assert r.status_code == 400

    with patch("app.services.captcha_service.captcha_service.verify_token", new_callable=AsyncMock,
               return_value={"success": True}):
        r = client.post("/api/auth/register", json={"username": "alice", "password": "correct horse 42", "captcha_token": "good"})
    assert r.status_code == 201


def test_paid_features_need_login(client):
    for method, path, body in [
        ("post", "/api/itinerary/generate", {"destination": "Amritsar"}),
        ("post", "/api/transport/search", {}),
        ("post", "/api/hotel/search", {}),
        ("post", "/api/area/summarize", {"area": "x"}),
        ("get", "/api/history", None),
    ]:
        r = getattr(client, method)(path, **({"json": body} if body is not None else {}))
        assert r.status_code == 401, (path, r.status_code)
        assert "log in" in r.json()["detail"].lower()

    # public features stay public
    assert client.post("/api/places/search", json={"location": "Manchester", "radius_km": 3}).status_code == 200
    assert client.get("/api/feedback").status_code == 200


def test_accounts_unavailable_message_when_database_missing(monkeypatch):
    from app import db

    monkeypatch.setattr(settings, "DATABASE_URL", None)
    monkeypatch.setattr(settings, "DB_HOST", None)
    db.reset_for_tests()
    with TestClient(app) as c:
        assert c.get("/api/auth/me").json() == {"authenticated": False, "user": None, "accounts_available": False}
        r = c.post("/api/auth/login", json={"username": "a", "password": "b"})
        assert r.status_code == 503 and "unavailable" in r.json()["detail"].lower()
        assert c.get("/api/health").json()["database"] == {"configured": False, "ready": False}


# ------------------------------------------------------------------ per-user History
def test_history_is_private_per_user_and_survives_logout(client):
    _register(client, "alice", "correct horse 42")
    created = client.post("/api/history", json={
        "feature_type": "itinerary", "title": "Delhi to Amritsar", "preview": "3 days",
        "payload": {"days": [1, 2, 3], "destination": "Amritsar"}}).json()
    client.post("/api/history", json={"feature_type": "places", "title": "Places: Manchester", "preview": "5", "payload": {"places": []}})
    client.post("/api/auth/logout")

    # logged out: nothing visible
    assert client.get("/api/history").status_code == 401

    # someone else registers: sees none of alice's data and cannot delete it
    _register(client, "bobby", "another strong pass 9")
    assert client.get("/api/history").json() == []
    assert client.delete(f"/api/history/{created['id']}").status_code == 404
    client.post("/api/auth/logout")

    # alice logs in again: her data is still there, intact
    client.post("/api/auth/login", json={"username": "alice", "password": "correct horse 42"})
    items = client.get("/api/history").json()
    assert {i["title"] for i in items} == {"Delhi to Amritsar", "Places: Manchester"}
    trip = next(i for i in items if i["feature_type"] == "itinerary")
    assert trip["payload"] == {"days": [1, 2, 3], "destination": "Amritsar"}
    assert client.get("/api/history?feature_type=places").json()[0]["title"] == "Places: Manchester"
    assert client.get("/api/history?feature_type=area_guide").json() == []

    assert client.delete(f"/api/history/{created['id']}").status_code == 200
    assert len(client.get("/api/history").json()) == 1


# ------------------------------------------------------------------ Reviews
def test_reviews_public_to_read_login_to_post_and_show_username(client):
    assert client.get("/api/feedback").json() == []
    assert client.post("/api/feedback/multi", json={"rating": 5, "comment": "great", "services": ["Area Guide"]}).status_code == 401

    _register(client, "carol", "reviewer secret 88")
    r = client.post("/api/feedback/multi", json={
        "rating": 4, "comment": "Nice itinerary and area guide", "services": ["Itinerary Planner", "Area Guide", "Area Guide"]})
    assert r.status_code == 201 and [i["service_used"] for i in r.json()] == ["Itinerary Planner", "Area Guide"]
    client.post("/api/auth/logout")

    listed = client.get("/api/feedback").json()  # public, no login
    assert len(listed) == 2 and {i["username"] for i in listed} == {"carol"}
    assert listed[0]["created_at"].endswith("+00:00")  # ISO UTC; browser shows local time


# ------------------------------------------------------------------ Saved sessions (drafts)
DRAFT = {"currentStep": 3, "source": "Delhi", "destination": "Amritsar", "outboundDate": "2026-11-10",
         "selectedOutbound": {"operator": "IndiGo"}, "hotelData": [{"name": "Hotel Ritz"}],
         "prefs": {"cuisines": ["Punjabi", "North Indian"], "pace": "relaxed"}}


def test_saved_session_roundtrip_update_and_privacy(client):
    assert client.get("/api/sessions").status_code == 401

    _register(client, "alice", "correct horse 42")
    saved = client.post("/api/sessions", json={"service": "itinerary", "title": "Delhi to Amritsar (step 3 of 5)", "state": DRAFT})
    assert saved.status_code == 200
    sid = saved.json()["id"]

    # overwrite the same draft (Save session pressed again)
    newer = dict(DRAFT, currentStep=4)
    again = client.post("/api/sessions", json={"id": sid, "service": "itinerary", "title": "Delhi to Amritsar (step 4 of 5)", "state": newer})
    assert again.json()["id"] == sid
    listed = client.get("/api/sessions?service=itinerary").json()
    assert len(listed) == 1 and listed[0]["title"].endswith("step 4 of 5)") and "state" not in listed[0]

    full = client.get(f"/api/sessions/{sid}").json()
    assert full["state"]["currentStep"] == 4 and full["state"]["prefs"]["cuisines"] == ["Punjabi", "North Indian"]

    client.post("/api/auth/logout")
    _register(client, "bobby", "another strong pass 9")
    assert client.get("/api/sessions").json() == []
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.delete(f"/api/sessions/{sid}").status_code == 404
    # bobby cannot overwrite alice's draft: it creates his own instead
    mine = client.post("/api/sessions", json={"id": sid, "service": "itinerary", "title": "mine", "state": {}}).json()
    assert mine["id"] != sid
    client.post("/api/auth/logout")

    # alice again: draft survives logout/login and can be deleted
    client.post("/api/auth/login", json={"username": "alice", "password": "correct horse 42"})
    assert client.get(f"/api/sessions/{sid}").json()["state"]["currentStep"] == 4
    assert client.delete(f"/api/sessions/{sid}").status_code == 200
    assert client.get("/api/sessions").json() == []


def test_saved_session_validation_and_limit(client):
    _register(client)
    assert client.post("/api/sessions", json={"service": "bogus", "title": "x", "state": {}}).status_code == 422
    for i in range(10):
        assert client.post("/api/sessions", json={"service": "area", "title": f"a{i}", "state": {}}).status_code == 200
    r = client.post("/api/sessions", json={"service": "area", "title": "one too many", "state": {}})
    assert r.status_code == 409 and "Delete one first" in r.json()["detail"]
    # other services have their own allowance
    assert client.post("/api/sessions", json={"service": "places", "title": "p", "state": {}}).status_code == 200


# ------------------------------------------------------------------ guest sessions
def test_guest_session_unlocks_planner_but_not_personal_features(client):
    # no login, no guest cookie: planner is blocked
    assert client.post("/api/transport/search", json={}).status_code == 401
    me = client.get("/api/auth/me").json()
    assert me["guest"] is False and me["authenticated"] is False

    r = client.post("/api/auth/guest", json={})
    assert r.status_code == 200 and settings.GUEST_COOKIE_NAME in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"]
    me = client.get("/api/auth/me").json()
    assert me["guest"] is True and me["authenticated"] is False and me["user"] is None

    # planner tools now pass the guard (an empty body is a 422 validation error, not a 401)
    assert client.post("/api/transport/search", json={}).status_code == 422
    # personal features stay login-only
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/sessions").status_code == 401
    assert client.post("/api/feedback", json={"rating": 5, "comment": "hello there", "service_used": "Area Guide"}).status_code == 401


def test_forged_or_expired_guest_cookie_is_rejected(client):
    from app.security import is_valid_guest_token, issue_guest_token
    good = issue_guest_token()
    assert is_valid_guest_token(good)
    assert not is_valid_guest_token(good[:-4] + "0000")
    assert not is_valid_guest_token("9999999999.abc.deadbeef")
    assert not is_valid_guest_token("1.abc." + good.split(".")[2])  # expired / wrong payload
    client.cookies.set(settings.GUEST_COOKIE_NAME, "9999999999.abc.deadbeef")
    assert client.post("/api/transport/search", json={}).status_code == 401


def test_logout_ends_guest_session(client):
    client.post("/api/auth/guest", json={})
    assert client.get("/api/auth/me").json()["guest"] is True
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").json()["guest"] is False


# ------------------------------------------------------------------ delete account
def test_delete_account_needs_correct_password_then_removes_everything(client):
    _register(client)
    client.post("/api/history", json={"feature_type": "itinerary", "title": "T", "preview": "p", "payload": {}})
    client.post("/api/sessions", json={"service": "itinerary", "title": "draft", "state": {}})

    wrong = client.post("/api/auth/delete-account", json={"password": "not my password"})
    assert wrong.status_code == 401 and "not deleted" in wrong.json()["detail"]
    assert client.get("/api/auth/me").json()["authenticated"] is True  # still there

    ok = client.post("/api/auth/delete-account", json={"password": "correct horse 42"})
    assert ok.status_code == 200 and ok.json()["status"] == "account_deleted"
    assert client.get("/api/auth/me").json()["authenticated"] is False
    # the account is really gone: logging in fails and the username is free again
    assert client.post("/api/auth/login", json={"username": "alice", "password": "correct horse 42"}).status_code == 401
    assert _register(client).status_code == 201


def test_delete_account_requires_login(client):
    assert client.post("/api/auth/delete-account", json={"password": "x"}).status_code == 401
