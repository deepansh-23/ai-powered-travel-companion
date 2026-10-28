"""Admin "Database" report: size, storage left, connections, memory, performance, limits and warnings.

Everything is read-only. Detailed numbers need PostgreSQL (the live Aiven database); on another database type (the
throw-away SQLite used by tests) the report says so and still shows the memory and disk of the app server.

Honest limits of what can be known:
  * A managed PostgreSQL (Aiven) does not tell its customers the RAM or the disk size of the machine it runs on. So
    "storage left" and "memory left" of the database need the plan sizes, which the admin enters once (stored in
    app_settings). Until then the page shows what the database uses and asks for the plan size.
  * Connections are different: the server reports its own maximum, so that bar is always real.
  * Memory and disk of the APP server (the Render service) are real numbers read from the operating system.
Limits only raise warnings on this page. They never block anyone.
"""

import asyncio
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import AppSetting

logger = logging.getLogger(__name__)

# key -> (default, minimum, maximum).  0 means "not set".
LIMITS: Dict[str, Tuple[int, int, int]] = {
    "storage_mb": (0, 0, 100_000_000),       # disk space of your database plan
    "memory_mb": (0, 0, 10_000_000),         # RAM of your database plan
    "connections": (0, 0, 100_000),          # 0 = use the maximum the server reports
}
LIMIT_PREFIX = "db_limit_"
QUERY_TIMEOUT = 5.0
WARN_PCT, CRIT_PCT = 80, 100
XID_WARN, XID_CRIT = 1_000_000_000, 1_500_000_000     # transaction-id age; PostgreSQL must act at about 2.1 billion

MB = 1024 * 1024


# ---------------------------------------------------------------- limits (stored in app_settings)
async def get_limits(db: AsyncSession) -> Dict[str, int]:
    rows = (await db.execute(select(AppSetting).where(AppSetting.key.like(LIMIT_PREFIX + "%")))).scalars().all()
    stored = {r.key[len(LIMIT_PREFIX):]: r.value for r in rows}
    out: Dict[str, int] = {}
    for key, (default, _lo, _hi) in LIMITS.items():
        try:
            out[key] = int(float(stored.get(key, default)))
        except (TypeError, ValueError):
            out[key] = default
    return out


async def save_limits(db: AsyncSession, limits: Dict[str, Any]) -> None:
    """Validates, then stores. Raises ValueError with a readable message."""
    clean: Dict[str, str] = {}
    for key, raw in (limits or {}).items():
        if key not in LIMITS:
            raise ValueError(f"Unknown limit: {key}")
        _default, lo, hi = LIMITS[key]
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number.")
        if v != v or v < lo or v > hi:
            raise ValueError(f"{key} must be between {lo:,} and {hi:,}.")
        clean[key] = str(int(round(v)))
    now = datetime.now(timezone.utc)
    for key, value in clean.items():
        full = LIMIT_PREFIX + key
        row = (await db.execute(select(AppSetting).where(AppSetting.key == full))).scalar_one_or_none()
        if row is None:
            db.add(AppSetting(key=full, value=value, description="Database monitor limit", updated_at=now))
        else:
            row.value, row.updated_at = value, now
    await db.commit()


# ---------------------------------------------------------------- app server memory and disk (from the operating system)
def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _kv_kb(text_blob: Optional[str], key: str) -> Optional[int]:
    """Value in bytes of a 'Key:   123 kB' line (as in /proc/meminfo and /proc/self/status)."""
    if not text_blob:
        return None
    for line in text_blob.splitlines():
        if line.startswith(key + ":"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _cgroup_memory() -> Tuple[Optional[int], Optional[int]]:
    """(limit, working set) of the container in bytes, or None when the server is not limited by a container."""
    limit = used = None
    v2_max = _read("/sys/fs/cgroup/memory.max")
    if v2_max is not None:
        v2_max = v2_max.strip()
        if v2_max.isdigit():
            limit = int(v2_max)
        cur = _read("/sys/fs/cgroup/memory.current")
        if cur and cur.strip().isdigit():
            used = int(cur.strip())
            stat = _read("/sys/fs/cgroup/memory.stat") or ""
            for line in stat.splitlines():
                if line.startswith("inactive_file "):
                    used = max(0, used - int(line.split()[1]))     # cache that can be dropped is not "used"
                    break
    else:
        v1_lim = _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        if v1_lim and v1_lim.strip().isdigit() and int(v1_lim.strip()) < (1 << 60):
            limit = int(v1_lim.strip())
        v1_use = _read("/sys/fs/cgroup/memory/memory.usage_in_bytes")
        if v1_use and v1_use.strip().isdigit():
            used = int(v1_use.strip())
    return limit, used


def app_resources() -> Dict[str, Any]:
    """Memory and disk of the machine the website runs on. Values are None when the system does not expose them."""
    meminfo = _read("/proc/meminfo")
    status = _read("/proc/self/status")
    total = _kv_kb(meminfo, "MemTotal")
    available = _kv_kb(meminfo, "MemAvailable")
    rss = _kv_kb(status, "VmRSS")
    peak = _kv_kb(status, "VmHWM")
    if rss is None:                                    # not Linux (a laptop): psutil if installed, else nothing
        try:
            import psutil  # type: ignore
            proc = psutil.Process()
            rss = proc.memory_info().rss
            vm = psutil.virtual_memory()
            total, available = vm.total, vm.available
        except Exception:
            pass
    cg_limit, cg_used = _cgroup_memory()
    if cg_limit and (total is None or cg_limit < total):
        limit, used = cg_limit, cg_used
        source = "container limit"
    else:
        limit = total
        used = (total - available) if (total is not None and available is not None) else None
        source = "server memory"
    free = (limit - used) if (limit is not None and used is not None) else None
    pct = round(used / limit * 100, 1) if (limit and used is not None) else None

    disk = None
    try:
        du = shutil.disk_usage(os.getcwd())
        disk = {"total": du.total, "used": du.used, "free": du.free, "pct": round(du.used / du.total * 100, 1) if du.total else None}
    except Exception:
        pass
    load = None
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass
    return {"process_rss": rss, "process_peak": peak, "memory_limit": limit, "memory_used": used, "memory_free": free,
            "memory_pct": pct, "memory_source": source, "disk": disk, "cpu_count": os.cpu_count(), "load_average": load}


# ---------------------------------------------------------------- PostgreSQL queries
async def _q(db: AsyncSession, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Runs one read-only query. A failure rolls the transaction back so the next query still works."""
    try:
        res = await asyncio.wait_for(db.execute(text(sql), params or {}), timeout=QUERY_TIMEOUT)
        return [dict(r) for r in res.mappings().all()]
    except Exception as exc:                            # noqa: BLE001 - one missing permission must not hide the rest
        logger.info("Database report query skipped: %s", type(exc).__name__)
        try:
            await db.rollback()
        except Exception:
            pass
        return []


def _setting_bytes(value: Any, unit: Optional[str]) -> Optional[int]:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    mult = {None: 1, "": 1, "B": 1, "kB": 1024, "8kB": 8192, "MB": MB, "GB": 1024 * MB}.get(unit)
    return int(n * mult) if mult else None


def _pool_state(db: AsyncSession) -> Optional[Dict[str, int]]:
    """How many of the app's own pooled connections are busy (None for the test database, which has no pool)."""
    try:
        pool = db.get_bind().pool                       # type: ignore[union-attr]
        size, out, over = pool.size(), pool.checkedout(), pool.overflow()
        return {"size": size, "in_use": out, "overflow": max(0, over), "max": size + getattr(pool, "_max_overflow", 0)}
    except Exception:
        return None


def _alert(level: str, title: str, detail: str) -> Dict[str, str]:
    return {"level": level, "title": title, "detail": detail}


def _fmt(b: Optional[float]) -> str:
    if b is None:
        return "unknown"
    n = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _pct_alert(alerts: List[Dict[str, str]], label: str, used: float, limit: float, fmt=lambda v: f"{v:,.0f}", hint: str = "") -> None:
    if not limit:
        return
    pct = used / limit * 100
    tail = f" {hint}" if hint else ""
    if pct >= CRIT_PCT:
        alerts.append(_alert("critical", f"{label}: limit reached", f"{fmt(used)} used of {fmt(limit)} ({pct:.0f}%).{tail}"))
    elif pct >= WARN_PCT:
        alerts.append(_alert("warning", f"{label}: close to the limit", f"{fmt(used)} used of {fmt(limit)} ({pct:.0f}%).{tail}"))


async def build_report(db: AsyncSession) -> Dict[str, Any]:
    """The whole page in one call. Never raises for a failing statistic: that part is simply left out."""
    limits = await get_limits(db)
    app = app_resources()
    alerts: List[Dict[str, str]] = []
    dialect = ""
    try:
        dialect = db.get_bind().dialect.name            # type: ignore[union-attr]
    except Exception:
        pass
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "engine": dialect or "unknown", "supported": dialect == "postgresql",
        "limits": limits, "app": app, "alerts": alerts, "reachable": False, "latency_ms": None,
        "server": None, "storage": None, "connections": None, "memory": None, "performance": None,
    }

    # ---- app server memory and disk (always available)
    if app["memory_pct"] is not None:
        _pct_alert(alerts, "Website server memory", app["memory_used"], app["memory_limit"], _fmt,
                   "When this fills up the server can restart. Consider a bigger plan or fewer parallel requests.")
    if app["disk"] and app["disk"]["pct"] is not None:
        _pct_alert(alerts, "Website server disk", app["disk"]["used"], app["disk"]["total"], _fmt)

    if not report["supported"]:
        report["message"] = ("Detailed database statistics need PostgreSQL. This server is using "
                             f"{dialect or 'another database type'}, so only the website server's memory and disk are shown.")
        return report

    # ---- reachability and latency
    t0 = time.perf_counter()
    ping = await _q(db, "SELECT version() AS v, pg_postmaster_start_time() AS started, current_database() AS name")
    report["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    if not ping:
        alerts.insert(0, _alert("critical", "Database not reachable", "The database did not answer. Check the Aiven service and the connection settings."))
        return report
    report["reachable"] = True
    started = ping[0].get("started")
    report["server"] = {
        "version": str(ping[0].get("v") or "").split(" on ")[0], "database": ping[0].get("name"),
        "started_at": started.isoformat() if hasattr(started, "isoformat") else None,
        "uptime_seconds": int((datetime.now(timezone.utc) - started).total_seconds()) if hasattr(started, "tzinfo") and started else None,
    }
    if report["latency_ms"] > 500:
        alerts.append(_alert("warning", "Database is slow to answer", f"A simple check took {report['latency_ms']:.0f} ms (healthy is under 100 ms)."))

    # ---- server settings (the memory the database is configured to use)
    cfg_rows = await _q(db, "SELECT name, setting, unit FROM pg_settings WHERE name IN "
                            "('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size','max_connections','superuser_reserved_connections')")
    cfg = {r["name"]: _setting_bytes(r["setting"], r["unit"]) if r["name"] not in ("max_connections", "superuser_reserved_connections")
           else int(r["setting"]) for r in cfg_rows}

    # ---- storage
    size_row = await _q(db, "SELECT pg_database_size(current_database()) AS b")
    used_bytes = int(size_row[0]["b"]) if size_row else None
    tables = await _q(db, "SELECT relname AS name, pg_total_relation_size(relid) AS total_bytes, n_live_tup AS rows, n_dead_tup AS dead_rows, "
                          "last_autovacuum, last_vacuum FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15")
    storage_limit = limits["storage_mb"] * MB
    pct = round(used_bytes / storage_limit * 100, 1) if (used_bytes is not None and storage_limit) else None
    report["storage"] = {
        "used_bytes": used_bytes, "limit_bytes": storage_limit or None, "free_bytes": (storage_limit - used_bytes) if (storage_limit and used_bytes is not None) else None,
        "pct": pct, "limit_is_set": bool(storage_limit),
        "tables": [{"name": t["name"], "total_bytes": int(t["total_bytes"] or 0), "rows": int(t["rows"] or 0), "dead_rows": int(t["dead_rows"] or 0)} for t in tables],
    }
    if used_bytes is not None:
        if storage_limit:
            _pct_alert(alerts, "Database storage", used_bytes, storage_limit, _fmt, "Delete old data or upgrade the plan before it fills up.")
        else:
            alerts.append(_alert("info", "Storage limit not set", f"The database uses {_fmt(used_bytes)}. Enter your plan's storage size below to see space left and get warnings."))
    bloated = [t for t in tables if (t["rows"] or 0) >= 1000 and (t["dead_rows"] or 0) > 0.2 * max(1, (t["rows"] or 0) + (t["dead_rows"] or 0))]
    if bloated:
        names = ", ".join(t["name"] for t in bloated[:4])
        alerts.append(_alert("warning", "Tables need cleaning (vacuum)", f"Many dead rows are wasting space in: {names}. PostgreSQL normally cleans these on its own; if this stays, run VACUUM."))

    # ---- connections
    act = await _q(db, "SELECT COALESCE(state, 'other') AS state, COUNT(*) AS n, "
                       "COALESCE(MAX(EXTRACT(EPOCH FROM (now() - state_change))) FILTER (WHERE state = 'idle in transaction'), 0) AS stuck_s, "
                       "COALESCE(MAX(EXTRACT(EPOCH FROM (now() - query_start))) FILTER (WHERE state = 'active'), 0) AS longest_s "
                       "FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1")
    by_state = {r["state"]: int(r["n"]) for r in act}
    current = sum(by_state.values())
    server_max = cfg.get("max_connections")
    reserved = cfg.get("superuser_reserved_connections") or 0
    usable = (server_max - reserved) if server_max else None
    conn_limit = limits["connections"] or usable
    pool = _pool_state(db)
    report["connections"] = {
        "current": current, "active": by_state.get("active", 0), "idle": by_state.get("idle", 0),
        "idle_in_transaction": by_state.get("idle in transaction", 0), "server_max": server_max, "reserved": reserved,
        "limit": conn_limit, "limit_source": "your setting" if limits["connections"] else "server maximum",
        "pct": round(current / conn_limit * 100, 1) if (conn_limit and current is not None) else None, "pool": pool,
    }
    if conn_limit:
        _pct_alert(alerts, "Database connections", current, conn_limit, lambda v: f"{v:,.0f}",
                   "New visitors may get errors when no connection is free.")
    stuck = max((float(r["stuck_s"] or 0) for r in act), default=0)
    if stuck >= 300:
        alerts.append(_alert("warning", "A connection is stuck waiting", f"One session has been 'idle in transaction' for {stuck / 60:.0f} minutes. It can hold locks and block others."))
    if pool and pool["max"] and pool["in_use"] >= pool["max"]:
        alerts.append(_alert("critical", "The app's connection pool is full", "Every pooled connection is busy, so new requests wait. Slow queries or too much traffic can cause this."))

    # ---- performance counters
    st = await _q(db, "SELECT blks_hit, blks_read, xact_commit, xact_rollback, deadlocks, temp_files, temp_bytes, stats_reset "
                      "FROM pg_stat_database WHERE datname = current_database()")
    xid = await _q(db, "SELECT age(datfrozenxid) AS a FROM pg_database WHERE datname = current_database()")
    perf: Dict[str, Any] = {"cache_hit_pct": None, "commits": None, "rollbacks": None, "deadlocks": None, "temp_files": None,
                            "temp_bytes": None, "xid_age": None, "xid_pct": None, "longest_query_seconds": None, "stats_since": None}
    if st:
        s = st[0]
        hit, read = int(s["blks_hit"] or 0), int(s["blks_read"] or 0)
        perf.update(commits=int(s["xact_commit"] or 0), rollbacks=int(s["xact_rollback"] or 0), deadlocks=int(s["deadlocks"] or 0),
                    temp_files=int(s["temp_files"] or 0), temp_bytes=int(s["temp_bytes"] or 0),
                    cache_hit_pct=round(hit / (hit + read) * 100, 2) if (hit + read) >= 10000 else None,
                    stats_since=s["stats_reset"].isoformat() if getattr(s["stats_reset"], "isoformat", None) else None)
        if perf["cache_hit_pct"] is not None and perf["cache_hit_pct"] < 90:
            alerts.append(_alert("warning", "Database memory cache is missing too often", f"Only {perf['cache_hit_pct']}% of reads come from memory (healthy is above 95%). The database may have too little memory for its data."))
        if perf["deadlocks"]:
            alerts.append(_alert("info", "Deadlocks happened", f"{perf['deadlocks']:,} deadlock(s) since the statistics were last reset. PostgreSQL resolves them, but frequent ones point to conflicting updates."))
    if xid:
        age = int(xid[0]["a"] or 0)
        perf["xid_age"], perf["xid_pct"] = age, round(age / 2_100_000_000 * 100, 1)
        if age >= XID_CRIT:
            alerts.append(_alert("critical", "Transaction ID wraparound is near", f"The database is {age:,} transactions from its last full clean. PostgreSQL stops accepting writes near 2.1 billion. Run VACUUM FREEZE or contact Aiven."))
        elif age >= XID_WARN:
            alerts.append(_alert("warning", "Transaction ID age is high", f"{age:,} of about 2.1 billion. Autovacuum should handle it, keep an eye on this."))
    perf["longest_query_seconds"] = round(max((float(r["longest_s"] or 0) for r in act), default=0), 1)
    if perf["longest_query_seconds"] >= 60:
        alerts.append(_alert("warning", "A query has been running for a long time", f"The longest running query is {perf['longest_query_seconds']:.0f} seconds old."))
    report["performance"] = perf

    # ---- memory the database is configured to use, and what the plan can give
    shared, work = cfg.get("shared_buffers"), cfg.get("work_mem")
    worst = (shared or 0) + (server_max or 0) * (work or 0) if (shared is not None and work is not None and server_max) else None
    plan_mem = limits["memory_mb"] * MB
    report["memory"] = {
        "shared_buffers": shared, "work_mem": work, "maintenance_work_mem": cfg.get("maintenance_work_mem"),
        "effective_cache_size": cfg.get("effective_cache_size"), "worst_case_bytes": worst, "plan_limit_bytes": plan_mem or None,
        "worst_case_pct": round(worst / plan_mem * 100, 1) if (worst and plan_mem) else None, "limit_is_set": bool(plan_mem),
        "note": ("Aiven does not report the RAM of the database machine, so 'memory left' cannot be read. "
                 "Shown instead: the memory PostgreSQL is configured to use, the cache hit rate, and the most it could use "
                 "if every connection used one work area at once."),
    }
    if worst and plan_mem and worst > plan_mem:
        alerts.append(_alert("warning", "Database memory settings exceed your plan", f"Settings allow up to about {_fmt(worst)}, more than the {_fmt(plan_mem)} of your plan. Heavy traffic could run it out of memory."))
    elif not plan_mem:
        alerts.append(_alert("info", "Plan memory not set", "Enter the RAM of your database plan below to compare it with what the database is configured to use."))

    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["level"], 3))
    return report
