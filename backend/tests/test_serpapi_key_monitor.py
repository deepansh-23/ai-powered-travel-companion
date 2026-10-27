"""Admin dashboard: which SerpApi key is in use, alerts for backup / exhausted keys, quota check for every key.

No network: the account endpoint and all searches are faked.
"""

import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from admin import usage as usage_report
from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service
from app.services import serpapi_client as sc
from app.services.usage_service import usage_recorder

KEY1, KEY2 = "MAIN-KEY-aaaaaaaaaaaaaaaaaaaa", "BACKUP-KEY-bbbbbbbbbbbbbbbbbbb"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    usage_recorder._buffer.clear()          # calls recorded by other tests must not leak into this test's report
    usage_recorder.failures.clear()
    usage_recorder._latency.clear()
    usage_recorder._recent_calls.clear()
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", KEY1)
    monkeypatch.setattr(settings, "SERP_API_KEY2", KEY2)
    client = sc.SerpApiClient()
    monkeypatch.setattr(usage_report, "serpapi_client", client)
    usage_report._serp_cache = (0.0, {})
    return client


@pytest.fixture
def client(_clean):
    return _clean


def _rest(client, key, kind="quota", minutes=60):
    kid = client._key_id(key)
    client._resting_until[kid] = time.time() + minutes * 60
    client._resting_kind[kid] = kind


async def _admin():
    async for db in get_db():
        user, _ = await auth_service.register(db, "adminuser", "Password123#")
        user.is_admin = True
        await db.commit()
        token = await auth_service.create_session(db, user)
        uid = user.id
        break
    stepup, _ = issue_admin_stepup_token(uid)
    return lambda: AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               cookies={settings.AUTH_COOKIE_NAME: token, ADMIN_STEPUP_COOKIE: stepup})


async def _alerts(admin=None):
    admin = admin or await _admin()
    async with admin() as c:
        r = (await c.get("/api/admin/usage")).json()
    return {a["title"]: a for a in r["alerts"]}, r


# ------------------------------------------------------------------ key status
def test_key_status_shows_state_and_reason_but_never_the_key(client):
    assert [(k["label"], k["state"]) for k in client.key_status()] == [("Main key", "ready"), ("Backup key", "ready")]
    _rest(client, KEY1, "quota", 59)
    st = client.key_status()
    assert st[0]["state"] == "resting" and st[0]["reason"] == "quota" and 59 <= st[0]["resting_minutes"] <= 60
    assert st[1]["state"] == "ready" and KEY1 not in str(st) and KEY2 not in str(st)


def test_a_real_switch_is_counted_and_marks_the_reason(client, monkeypatch):
    class Resp:
        def __init__(self, status, body): self.status_code, self._b = status, body
        def json(self): return self._b
    class Http:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            return Resp(200, {"error": "Your account has run out of searches."}) if params["api_key"] == KEY1 else Resp(200, {"best_flights": []})
    monkeypatch.setattr(sc.httpx, "AsyncClient", Http)
    asyncio.run(client.search({"engine": "google_flights", "q": "x"}))
    assert client.switch_count == 1 and client.last_switch_at
    assert client.key_status()[0]["reason"] == "quota"


# ------------------------------------------------------------------ alerts
@pytest.mark.asyncio
async def test_no_key_alert_when_everything_is_healthy():
    titles, r = await _alerts()
    assert not any("SerpApi" in t for t in titles)
    assert [k["state"] for k in r["serpapi_keys"]] == ["ready", "ready"]


@pytest.mark.asyncio
async def test_warning_when_the_backup_key_is_in_use(client):
    _rest(client, KEY1, "quota", 30)
    titles, r = await _alerts()
    a = titles["SerpApi backup key is in use"]
    assert a["level"] == "warning" and "out of searches" in a["detail"] and "30 min" in a["detail"] or "31 min" in a["detail"]
    assert KEY1 not in str(r) and KEY2 not in str(r)


@pytest.mark.asyncio
async def test_critical_when_both_keys_are_exhausted(client):
    _rest(client, KEY1, "quota")
    _rest(client, KEY2, "invalid")
    titles, _ = await _alerts()
    assert titles["SerpApi: no key is working"]["level"] == "critical"


@pytest.mark.asyncio
async def test_critical_when_the_only_key_is_exhausted_and_info_when_only_the_backup_rests(client, monkeypatch):
    admin = await _admin()
    monkeypatch.setattr(settings, "SERP_API_KEY2", None)
    _rest(client, KEY1, "rate")
    titles, _ = await _alerts(admin)
    assert titles["SerpApi key is exhausted"]["level"] == "critical"
    monkeypatch.setattr(settings, "SERP_API_KEY2", KEY2)
    client._resting_until.clear()
    _rest(client, KEY2, "rate")
    titles, _ = await _alerts(admin)
    assert titles["SerpApi backup key is resting"]["level"] == "info"


# ------------------------------------------------------------------ quota check for every key
def _fake_account(monkeypatch, per_key):
    class Resp:
        def __init__(self, status, body): self.status_code, self._b = status, body
        def json(self): return self._b
    class Http:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            assert url == "https://serpapi.com/account"
            item = per_key[params["api_key"]]
            if isinstance(item, Exception):
                raise item
            return item if isinstance(item, Resp) else Resp(200, item)
    monkeypatch.setattr(usage_report.httpx, "AsyncClient", Http)
    return Resp


@pytest.mark.asyncio
async def test_quota_check_reports_each_key_and_never_returns_a_key(monkeypatch):
    _fake_account(monkeypatch, {
        KEY1: {"plan_name": "Free", "searches_per_month": 250, "this_month_usage": 240, "total_searches_left": 10},
        KEY2: {"plan_name": "Free", "searches_per_month": 250, "this_month_usage": 20, "total_searches_left": 230},
    })
    out = await usage_report.serpapi_account(force=True)
    assert [(k["label"], k["left"]) for k in out["keys"]] == [("Main key", 10), ("Backup key", 230)]
    assert out["left"] == 10 and out["available"]                         # first key at the top level: earlier shape kept
    assert KEY1 not in str(out) and KEY2 not in str(out)
    titles, _ = await _alerts()                                           # cached result feeds the alerts, labelled per key
    assert titles["SerpApi main key: searches almost gone"]["level"] == "critical"
    assert not any("backup key: searches" in t for t in titles)


@pytest.mark.asyncio
async def test_one_failing_key_does_not_hide_the_other(monkeypatch):
    _fake_account(monkeypatch, {KEY1: RuntimeError("network down api_key=SECRETSECRETSECRETSECRET1234567"),
                                KEY2: {"plan_name": "Dev", "searches_per_month": 5000, "this_month_usage": 1, "total_searches_left": 4999}})
    out = await usage_report.serpapi_account(force=True)
    assert out["available"] is True
    assert out["keys"][0]["available"] is False and "SECRET" not in str(out)
    assert out["keys"][1]["left"] == 4999


@pytest.mark.asyncio
async def test_quota_check_with_no_key_is_clean(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", None)
    monkeypatch.setattr(settings, "SERP_API_KEY2", None)
    out = await usage_report.serpapi_account(force=True)
    assert out["available"] is False and out["keys"] == []


@pytest.mark.asyncio
async def test_endpoints_still_need_an_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.post("/api/admin/usage/serpapi-quota")).status_code == 401
        assert (await anon.get("/api/admin/usage")).status_code == 401
