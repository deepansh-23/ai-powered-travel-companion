"""Admin "Database" page: report on PostgreSQL (faked), fallback on other databases, limits, warnings, access rules."""

import datetime as dt

import pytest
from httpx import ASGITransport, AsyncClient

from admin import database as db_report
from admin.permissions import ADMIN_STEPUP_COOKIE, issue_admin_stepup_token
from app.config import settings
from app.db import get_db
from app.main import app
from app.security import require_user, require_user_or_guest
from app.services import auth_service


@pytest.fixture(autouse=True)
def _clean():
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(require_user_or_guest, None)
    yield


async def _admin():
    async for db in get_db():
        user, _ = await auth_service.register(db, "dbadmin", "Password123#")
        user.is_admin = True
        await db.commit()
        token = await auth_service.create_session(db, user)
        uid = user.id
        break
    stepup, _ = issue_admin_stepup_token(uid)
    return lambda: AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                               cookies={settings.AUTH_COOKIE_NAME: token, ADMIN_STEPUP_COOKIE: stepup})


# ---------------------------------------------------------------- a fake PostgreSQL session
class _Res:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Pool:
    _max_overflow = 5

    def size(self):
        return 5

    def checkedout(self):
        return 10

    def overflow(self):
        return 5


class _Bind:
    class dialect:
        name = "postgresql"

    pool = _Pool()


class _FakePg:
    """Answers the report's queries from the SQL text, like a small PostgreSQL would."""

    def __init__(self, fail=()):
        self.fail = fail

    def get_bind(self):
        return _Bind()

    async def rollback(self):
        pass

    async def execute(self, sql, params=None):
        q = str(sql)
        now = dt.datetime.now(dt.timezone.utc)
        if any(f in q for f in self.fail):
            raise RuntimeError("permission denied")
        if "version()" in q:
            return _Res([{"v": "PostgreSQL 16.3 on x86_64", "started": now - dt.timedelta(days=3), "name": "defaultdb"}])
        if "pg_settings" in q:
            return _Res([{"name": "shared_buffers", "setting": "16384", "unit": "8kB"}, {"name": "work_mem", "setting": "4096", "unit": "kB"},
                         {"name": "maintenance_work_mem", "setting": "65536", "unit": "kB"}, {"name": "effective_cache_size", "setting": "524288", "unit": "8kB"},
                         {"name": "max_connections", "setting": "25", "unit": None}, {"name": "superuser_reserved_connections", "setting": "3", "unit": None}])
        if "pg_database_size" in q:
            return _Res([{"b": 900 * 1024 * 1024}])
        if "pg_stat_user_tables" in q:
            return _Res([{"name": "users", "total_bytes": 500, "rows": 5000, "dead_rows": 2500, "last_autovacuum": None, "last_vacuum": None}])
        if "pg_stat_activity" in q:
            return _Res([{"state": "active", "n": 3, "stuck_s": 0, "longest_s": 90}, {"state": "idle", "n": 19, "stuck_s": 0, "longest_s": 0},
                         {"state": "idle in transaction", "n": 1, "stuck_s": 600, "longest_s": 0}])
        if "pg_stat_database" in q:
            return _Res([{"blks_hit": 80000, "blks_read": 20000, "xact_commit": 10, "xact_rollback": 1, "deadlocks": 2,
                          "temp_files": 0, "temp_bytes": 0, "stats_reset": now}])
        if "datfrozenxid" in q:
            return _Res([{"a": 1_600_000_000}])
        raise RuntimeError(q)


def _titles(report):
    return {a["title"]: a["level"] for a in report["alerts"]}


@pytest.mark.asyncio
async def test_postgres_report_numbers_limits_and_warnings(monkeypatch):
    async def limits(_db):
        return {"storage_mb": 1024, "memory_mb": 512, "connections": 0}
    monkeypatch.setattr(db_report, "get_limits", limits)
    r = await db_report.build_report(_FakePg())
    assert r["supported"] and r["reachable"] and r["server"]["database"] == "defaultdb"
    assert r["storage"]["pct"] == 87.9 and r["storage"]["free_bytes"] == (1024 - 900) * 1024 * 1024
    assert r["connections"]["current"] == 23 and r["connections"]["limit"] == 22 and r["connections"]["pct"] > 100   # 25 max - 3 reserved
    assert r["memory"]["shared_buffers"] == 16384 * 8192 and r["memory"]["work_mem"] == 4096 * 1024
    assert r["performance"]["cache_hit_pct"] == 80.0 and r["performance"]["deadlocks"] == 2
    t = _titles(r)
    assert t["Database connections: limit reached"] == "critical"
    assert t["Database storage: close to the limit"] == "warning"
    assert t["Transaction ID wraparound is near"] == "critical"
    assert "The app's connection pool is full" in t and "A connection is stuck waiting" in t
    assert "Database memory cache is missing too often" in t and "Tables need cleaning (vacuum)" in t
    assert [a["level"] for a in r["alerts"]] == sorted((a["level"] for a in r["alerts"]), key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x])


@pytest.mark.asyncio
async def test_unset_plan_sizes_give_info_not_warnings(monkeypatch):
    async def limits(_db):
        return {"storage_mb": 0, "memory_mb": 0, "connections": 0}
    monkeypatch.setattr(db_report, "get_limits", limits)
    r = await db_report.build_report(_FakePg())
    t = _titles(r)
    assert t["Storage limit not set"] == "info" and t["Plan memory not set"] == "info"
    assert r["storage"]["free_bytes"] is None and r["storage"]["limit_is_set"] is False


@pytest.mark.asyncio
async def test_one_failing_statistic_does_not_hide_the_rest(monkeypatch):
    async def limits(_db):
        return {"storage_mb": 0, "memory_mb": 0, "connections": 0}
    monkeypatch.setattr(db_report, "get_limits", limits)
    r = await db_report.build_report(_FakePg(fail=("pg_stat_user_tables", "datfrozenxid")))
    assert r["reachable"] and r["storage"]["tables"] == [] and r["performance"]["xid_age"] is None
    assert r["storage"]["used_bytes"] == 900 * 1024 * 1024


@pytest.mark.asyncio
async def test_unreachable_database_is_critical(monkeypatch):
    async def limits(_db):
        return {"storage_mb": 0, "memory_mb": 0, "connections": 0}
    monkeypatch.setattr(db_report, "get_limits", limits)
    r = await db_report.build_report(_FakePg(fail=("version()",)))
    assert r["reachable"] is False and r["alerts"][0]["level"] == "critical"


def test_unit_conversion_and_size_text():
    assert db_report._setting_bytes("16384", "8kB") == 16384 * 8192
    assert db_report._setting_bytes("64", "MB") == 64 * 1024 * 1024
    assert db_report._setting_bytes("x", "kB") is None
    assert db_report._fmt(1536 * 1024 * 1024) == "1.5 GB" and db_report._fmt(None) == "unknown"


# ---------------------------------------------------------------- the real endpoints (test database is not PostgreSQL)
@pytest.mark.asyncio
async def test_endpoint_needs_admin_and_falls_back_on_other_databases():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anon:
        assert (await anon.get("/api/admin/database")).status_code == 401
        assert (await anon.get("/api/admin/database/settings")).status_code == 401
        assert (await anon.put("/api/admin/database/settings", json={"limits": {}})).status_code == 401
    admin = await _admin()
    async with admin() as c:
        r = await c.get("/api/admin/database")
        assert r.status_code == 200
        body = r.json()
        assert body["supported"] is False and "PostgreSQL" in body["message"] and "memory_used" in body["app"]


@pytest.mark.asyncio
async def test_plan_limits_save_validate_and_cannot_store_anything_else():
    admin = await _admin()
    async with admin() as c:
        r = await c.put("/api/admin/database/settings", json={"limits": {"storage_mb": 1024, "memory_mb": 512, "connections": 20}})
        assert r.status_code == 200 and r.json()["limits"] == {"storage_mb": 1024, "memory_mb": 512, "connections": 20}
        assert (await c.get("/api/admin/database/settings")).json()["limits"]["storage_mb"] == 1024
        assert (await c.put("/api/admin/database/settings", json={"limits": {"api_key": 1}})).status_code == 400
        assert (await c.put("/api/admin/database/settings", json={"limits": {"storage_mb": "lots"}})).status_code == 400
        assert (await c.put("/api/admin/database/settings", json={"limits": {"storage_mb": -5}})).status_code == 400
        assert (await c.put("/api/admin/database/settings", json={"limits": {}, "DB_PASSWORD": "x"})).status_code == 400
        assert (await c.put("/api/admin/database/settings", json={"nothing": 1})).status_code == 400
        