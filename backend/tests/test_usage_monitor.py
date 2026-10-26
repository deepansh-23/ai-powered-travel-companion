"""AI & API usage monitor: recording, spend estimate, limits and alerts, settings validation, privacy."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from admin import usage as usage_report
from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db
from app.db_models import ApiUsageDaily
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service
from app.services.usage_service import UsageRecorder, scrub, usage_recorder


@pytest.fixture(autouse=True)
def _clean():
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    usage_recorder._buffer.clear()
    usage_recorder.failures.clear()
    usage_recorder._latency.clear()
    usage_recorder._recent_calls.clear()
    usage_report._serp_cache = (0.0, {})
    yield


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


async def _seed(rows):
    async for db in get_db():
        for day, provider, model, feature, outcome, n, ms, tin, tout in rows:
            db.add(ApiUsageDaily(day=day, provider=provider, model=model, feature=feature, outcome=outcome,
                                 requests=n, total_ms=ms, max_ms=ms // max(n, 1) * 2, tokens_in=tin, tokens_out=tout))
        await db.commit()
        break


TODAY = lambda: datetime.now(timezone.utc).date()


# ----------------------------------------------------------------- recording and privacy
def test_scrub_hides_keys_tokens_and_long_text():
    dirty = "GET https://x/api?apiKey=AIzaSyA1234567890abcdefghijklmnop&q=1 failed: Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789"
    clean = scrub(dirty)
    assert "AIza" not in clean and "abcdefghijklmnop" not in clean and "[hidden]" in clean
    assert len(scrub("x " * 500)) <= 220


def test_track_counts_failures_statuses_and_not_found_as_success():
    r = UsageRecorder()
    with r.track("serpapi", "google_flights") as u:
        u.status = 200
    with r.track("railradar", "lookup") as u:
        u.status = 404                      # "nothing found" is a normal answer
    with r.track("geoapify", "places") as u:
        u.status = 429                      # provider refused: a failure
    with pytest.raises(RuntimeError):
        with r.track("geoapify", "geocode"):
            raise RuntimeError("boom")
    by = {(k[1], k[2], k[4]): v[0] for k, v in r._buffer.items()}
    assert by == {("serpapi", "google_flights", "ok"): 1, ("railradar", "lookup", "ok"): 1,
                  ("geoapify", "places", "error"): 1, ("geoapify", "geocode", "error"): 1}
    assert [f["status"] for f in r.failures] == [None, 429]              # newest first
    assert r.failures[0]["error"] == "boom" and r.calls_last_hour() == 4


def test_buffer_is_bounded_and_failure_list_is_capped():
    r = UsageRecorder()
    for i in range(6000):
        r.record("gemini", f"m{i}", False, 5)
    assert len(r._buffer) <= 5000 and len(r.failures) == 100


@pytest.mark.asyncio
async def test_gemini_attempts_are_recorded_with_tokens(monkeypatch):
    from app.services import ai_service as ai_mod
    from app.services.ai_service import ai_service

    class Usage: prompt_token_count, candidates_token_count, thoughts_token_count = 1200, 300, 100
    class Resp:
        text = " {} "
        usage_metadata = Usage()
    class Models:
        calls = 0
        def generate_content(self, model, contents, config):
            Models.calls += 1
            if model == "bad-model":
                raise RuntimeError("404 model not found")
            return Resp()
    class Client:
        def __init__(self, api_key): self.models = Models()
    monkeypatch.setattr(ai_mod, "_gemini_available", True)
    monkeypatch.setattr(ai_mod, "_use_legacy_genai", False)
    monkeypatch.setattr(ai_mod, "genai_client", type("G", (), {"Client": Client}), raising=False)
    monkeypatch.setattr(ai_mod, "genai_types", type("T", (), {"GenerateContentConfig": lambda **k: None}), raising=False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ai_service, "_get_candidate_models", lambda: ["bad-model", "gemini-2.5-flash"])
    assert ai_service._generate_with_fallback("hi") == "{}"
    rows = {(k[2], k[4]): v for k, v in usage_recorder._buffer.items()}
    assert rows[("bad-model", "error")][0] == 1
    ok = rows[("gemini-2.5-flash", "ok")]
    assert ok[0] == 1 and ok[3] == 1200 and ok[4] == 400                 # thinking tokens count as output


# ----------------------------------------------------------------- the report
@pytest.mark.asyncio
async def test_report_models_features_costs_and_unpriced():
    admin = await _admin()
    t = TODAY()
    await _seed([
        (t, "gemini", "gemini-2.5-flash", "itinerary", "ok", 8, 16000, 80_000, 20_000),
        (t, "gemini", "gemini-2.5-flash", "itinerary", "error", 2, 4000, 0, 0),
        (t, "gemini", "gemini-2.5-flash", "area", "ok", 5, 5000, 10_000, 5_000),
        (t, "gemini", "gemini-9-mystery", "area", "ok", 1, 900, 1000, 1000),
        (t, "serpapi", "google_flights", "itinerary", "ok", 6, 6000, 0, 0),
        (t, "serpapi", "google_hotels", "itinerary", "error", 1, 700, 0, 0),
        (t - timedelta(days=2), "geoapify", "places", "places", "ok", 40, 8000, 0, 0),
    ])
    async with admin() as c:
        r = (await c.get("/api/admin/usage?days=7")).json()
        s = r["summary"]
        assert (s["ai_requests"], s["ai_ok"], s["ai_failed"]) == (16, 14, 2) and s["success_rate"] == 87.5
        assert s["avg_ms"] == round((16000 + 4000 + 5000 + 900) / 16)
        # 2.5-flash: (90_000*0.30 + 25_000*2.50)/1e6 = 0.0895 USD ; mystery model has no price
        assert s["est_cost_usd"] == pytest.approx(0.0895, abs=1e-6) and s["est_cost_inr"] == pytest.approx(0.0895 * 85, abs=0.01)
        assert s["unpriced_models"] == ["gemini-9-mystery"]
        m = {x["model"]: x for x in r["by_model"]}
        assert m["gemini-2.5-flash"]["requests"] == 15 and m["gemini-2.5-flash"]["failed"] == 2 and m["gemini-9-mystery"]["cost_usd"] is None
        f = {x["feature"]: x for x in r["by_feature"]}
        assert f["itinerary"]["requests"] == 10 and f["itinerary"]["models"] == [{"model": "gemini-2.5-flash", "requests": 10, "failed": 2}]
        ext = {x["provider"]: x for x in r["external"]}
        assert ext["serpapi"]["requests"] == 7 and ext["serpapi"]["failed"] == 1 and ext["geoapify"]["requests"] == 40
        assert ext["serpapi"]["endpoints"][0]["endpoint"] == "google_flights" or ext["serpapi"]["endpoints"][0]["endpoint"] == "google_hotels"
        assert len(r["series"]) == 7 and r["series"][-1]["ai_failed"] == 2
        assert any(a["level"] == "info" for a in r["alerts"])               # unpriced model note


@pytest.mark.asyncio
async def test_limits_trigger_warning_and_critical_alerts_and_validate():
    admin = await _admin()
    t = TODAY()
    await _seed([(t, "gemini", "gemini-2.5-flash", "itinerary", "ok", 90, 9000, 90_000, 20_000),
                 (t, "serpapi", "google_flights", "itinerary", "ok", 50, 5000, 0, 0)])
    async with admin() as c:
        r = await c.put("/api/admin/usage/settings", json={"limits": {"ai_daily_requests": 100, "serpapi_monthly_requests": 50}})
        assert r.status_code == 200 and r.json()["limits"]["ai_daily_requests"] == 100
        alerts = {a["title"]: a["level"] for a in (await c.get("/api/admin/usage")).json()["alerts"]}
        titles = " | ".join(alerts)
        assert "AI requests today: close to the limit" in titles and alerts["SerpApi (flights and hotels): limit reached"] == "critical"
        # validation: unknown keys, bad numbers, out of range, extra top-level fields, bad prices
        assert (await c.put("/api/admin/usage/settings", json={"limits": {"api_key": 1}})).status_code == 400
        assert (await c.put("/api/admin/usage/settings", json={"limits": {"ai_daily_requests": "lots"}})).status_code == 400
        assert (await c.put("/api/admin/usage/settings", json={"limits": {"error_rate_percent": 500}})).status_code == 400
        assert (await c.put("/api/admin/usage/settings", json={"GEMINI_API_KEY": "x"})).status_code == 400
        assert (await c.put("/api/admin/usage/settings", json={"prices": {"bad name!": [1, 2]}})).status_code == 400
        assert (await c.put("/api/admin/usage/settings", json={"prices": {"m": [-1, 2]}})).status_code == 400


@pytest.mark.asyncio
async def test_custom_price_changes_the_estimate_and_cost_alert():
    admin = await _admin()
    await _seed([(TODAY(), "gemini", "gemini-9-mystery", "area", "ok", 4, 4000, 1_000_000, 1_000_000)])
    async with admin() as c:
        assert (await c.get("/api/admin/usage")).json()["summary"]["est_cost_usd"] is None
        await c.put("/api/admin/usage/settings", json={"prices": {"gemini-9-mystery": [1.0, 2.0]}, "limits": {"ai_monthly_cost_usd": 3}})
        r = (await c.get("/api/admin/usage")).json()
        assert r["summary"]["est_cost_usd"] == 3.0
        assert any(a["level"] == "critical" and "spend" in a["title"] for a in r["alerts"])


@pytest.mark.asyncio
async def test_unusual_traffic_and_error_rate_alerts():
    admin = await _admin()
    t = TODAY()
    rows = [(t - timedelta(days=i), "geoapify", "places", "places", "ok", 20, 2000, 0, 0) for i in range(1, 6)]
    rows += [(t, "geoapify", "places", "places", "ok", 90, 9000, 0, 0), (t, "geoapify", "places", "places", "error", 40, 4000, 0, 0)]
    await _seed(rows)
    async with admin() as c:
        titles = {a["title"]: a for a in (await c.get("/api/admin/usage")).json()["alerts"]}
        assert titles["Unusually high traffic today"]["level"] == "critical"          # 130 vs about 20 per day (6.5x)
        assert "Geoapify (places and maps): many failures today" in titles              # 40 of 130 failed


@pytest.mark.asyncio
async def test_failures_list_has_no_secrets_and_endpoints_need_admin():
    usage_recorder.record("serpapi", "google_flights", False, 12, status=401,
                          error="Invalid key api_key=SECRETSECRETSECRETSECRET123456789012 rejected", feature="itinerary")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        for path in ("/api/admin/usage", "/api/admin/usage/settings"):
            assert (await anon.get(path)).status_code == 401
        assert (await anon.post("/api/admin/usage/serpapi-quota")).status_code == 401
    admin = await _admin()
    async with admin() as c:
        body = (await c.get("/api/admin/usage")).text
        assert "SECRETSECRET" not in body and "[hidden]" in body
        assert (await c.get("/api/admin/usage?start=2026-02-01&end=2026-01-01")).status_code == 400


@pytest.mark.asyncio
async def test_serpapi_account_check_is_safe_without_a_key_and_parses_the_answer(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "")
    assert (await usage_report.serpapi_account(force=True))["available"] is False

    class Resp:
        status_code = 200
        def json(self): return {"plan_name": "Free", "searches_per_month": 250, "this_month_usage": 240, "total_searches_left": 10}
    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None): return Resp()
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "real-looking-key-123")
    monkeypatch.setattr(usage_report.httpx, "AsyncClient", Client)
    out = await usage_report.serpapi_account(force=True)
    assert out["available"] and out["left"] == 10 and "key" not in str(out).lower().replace("searches", "")
    admin = await _admin()
    async with admin() as c:
        alerts = (await c.get("/api/admin/usage")).json()["alerts"]
        assert any(a["level"] == "critical" and "SerpApi" in a["title"] for a in alerts)     # 10 of 250 left
