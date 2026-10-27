"""Admin "AI & API Usage" monitor: requests, failures, response times, estimated AI spend, quota warnings, alerts.

Everything comes from the anonymous counters in api_usage_daily (see app.services.usage_service) plus the
admin-set limits and model prices stored in app_settings. Prices are estimates at published list prices; the
real bill (or a free tier) can differ.
"""

import json
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db_models import ApiUsageDaily, AppSetting
from app.services.serpapi_client import serpapi_client
from app.services.usage_service import AI_PROVIDER, scrub, today, usage_recorder

logger = logging.getLogger(__name__)

EXTERNAL = ("serpapi", "geoapify", "railradar", "osrm", "recaptcha")
PROVIDER_LABELS = {"gemini": "Gemini (AI)", "serpapi": "SerpApi (flights and hotels)", "geoapify": "Geoapify (places and maps)",
                   "railradar": "RailRadar (trains)", "osrm": "OSRM (routes)", "recaptcha": "reCAPTCHA"}

# key -> (default, minimum, maximum, is_integer).  0 means "no limit set".
LIMITS: Dict[str, Tuple[float, float, float, bool]] = {
    "ai_daily_requests": (0, 0, 1_000_000, True),
    "ai_monthly_cost_usd": (0, 0, 100_000, False),
    "serpapi_monthly_requests": (0, 0, 10_000_000, True),
    "geoapify_daily_requests": (0, 0, 10_000_000, True),
    "railradar_daily_requests": (0, 0, 10_000_000, True),
    "hourly_burst_requests": (0, 0, 1_000_000, True),
    "error_rate_percent": (25, 1, 100, True),
    "usd_to_inr": (85.0, 1, 1000, False),
}
LIMIT_PREFIX = "usage_limit_"
PRICES_KEY = "usage_prices"

# USD per 1 million tokens (input, output). Starter list prices checked in Oct 2026 against public pricing pages; they
# change often, so they are editable on the page. Models without a price are shown without a cost estimate.
DEFAULT_PRICES: Dict[str, Tuple[float, float]] = {
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3-flash": (0.50, 3.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.6-flash": (1.50, 7.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.1-pro": (2.00, 12.00),
}
_MODEL_NAME = re.compile(r"^[A-Za-z0-9._\-]{1,60}$")


# ---------------------------------------------------------------- limits and prices (stored in app_settings)
async def get_limits(db: AsyncSession) -> Dict[str, float]:
    rows = (await db.execute(select(AppSetting).where(AppSetting.key.like(LIMIT_PREFIX + "%")))).scalars().all()
    stored = {r.key[len(LIMIT_PREFIX):]: r.value for r in rows}
    out: Dict[str, float] = {}
    for key, (default, lo, hi, is_int) in LIMITS.items():
        try:
            v = float(stored.get(key, default))
        except (TypeError, ValueError):
            v = float(default)
        out[key] = int(v) if is_int else v
    return out


async def get_prices(db: AsyncSession) -> Dict[str, Tuple[float, float]]:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == PRICES_KEY))).scalar_one_or_none()
    prices = dict(DEFAULT_PRICES)
    if row and row.value:
        try:
            for name, pair in json.loads(row.value).items():
                if _MODEL_NAME.match(name) and isinstance(pair, (list, tuple)) and len(pair) == 2:
                    prices[name] = (float(pair[0]), float(pair[1]))
        except Exception:
            logger.warning("Stored usage prices could not be read; using defaults.")
    return prices


async def _upsert(db: AsyncSession, key: str, value: str, description: str) -> None:
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(AppSetting(key=key, value=value, description=description, updated_at=now))
    else:
        row.value, row.updated_at = value, now


async def save_limits_and_prices(db: AsyncSession, limits: Optional[Dict[str, Any]], prices: Optional[Dict[str, Any]]) -> None:
    """Validates then stores. Raises ValueError with a readable message."""
    clean_limits: Dict[str, str] = {}
    for key, raw in (limits or {}).items():
        if key not in LIMITS:
            raise ValueError(f"Unknown limit: {key}")
        default, lo, hi, is_int = LIMITS[key]
        try:
            v = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number.")
        if v != v or v < lo or v > hi:
            raise ValueError(f"{key} must be between {lo:g} and {hi:g}.")
        clean_limits[key] = str(int(round(v))) if is_int else str(round(v, 4))
    clean_prices: Optional[Dict[str, List[float]]] = None
    if prices is not None:
        if len(prices) > 60:
            raise ValueError("Too many model prices (at most 60).")
        clean_prices = {}
        for name, pair in prices.items():
            if not _MODEL_NAME.match(str(name)):
                raise ValueError(f"Invalid model name: {str(name)[:40]}")
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError(f"Price for {name} needs an input and an output value.")
            try:
                pin, pout = float(pair[0]), float(pair[1])
            except (TypeError, ValueError):
                raise ValueError(f"Prices for {name} must be numbers.")
            if not (0 <= pin <= 1000 and 0 <= pout <= 1000):
                raise ValueError(f"Prices for {name} must be between 0 and 1000 USD per million tokens.")
            clean_prices[name] = [pin, pout]
    for key, v in clean_limits.items():
        await _upsert(db, LIMIT_PREFIX + key, v, "Usage monitor limit")
    if clean_prices is not None:
        await _upsert(db, PRICES_KEY, json.dumps(clean_prices), "Estimated AI model prices (USD per 1M tokens)")
    await db.commit()


def price_for(model: str, prices: Dict[str, Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    name = (model or "").replace("models/", "")
    if name in prices:
        return prices[name]
    for key, val in prices.items():       # dated / preview variants of a known model, never a different tier
        if name.startswith(key + "-preview") or re.fullmatch(re.escape(key) + r"-\d{2,}.*", name):
            return val
    return None


def cost_usd(model: str, tin: int, tout: int, prices: Dict[str, Tuple[float, float]]) -> Optional[float]:
    p = price_for(model, prices)
    if p is None:
        return None
    return (tin * p[0] + tout * p[1]) / 1_000_000


# ---------------------------------------------------------------- SerpApi: ask the provider how many searches are left
_serp_cache: Tuple[float, Dict[str, Any]] = (0.0, {})


async def _account_for(key: str) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://serpapi.com/account", params={"api_key": key})
        if resp.status_code != 200:
            return {"available": False, "message": f"SerpApi account check failed (HTTP {resp.status_code})."}
        d = resp.json()
        return {
            "available": True,
            "plan": d.get("plan_name") or d.get("plan_id"),
            "searches_per_month": d.get("searches_per_month"),
            "used_this_month": d.get("this_month_usage"),
            "left": d.get("total_searches_left", d.get("plan_searches_left")),
        }
    except Exception as exc:
        return {"available": False, "message": "SerpApi account check failed: " + scrub(exc, 120)}


async def serpapi_account(force: bool = False) -> Dict[str, Any]:
    """Asks SerpApi how many searches each configured key has left (its free account endpoint; costs no search).

    Cached for 10 minutes. Never returns a key. The first key's numbers are also given at the top level, so the
    result keeps its earlier shape; `keys` lists every key (main, then backup).
    """
    global _serp_cache
    if not force and _serp_cache[1] and time.time() - _serp_cache[0] < 600:
        return _serp_cache[1]
    try:
        keys = serpapi_client._configured_keys()
    except RuntimeError:
        return {"available": False, "message": "SERPAPI_API_KEY is not configured.", "keys": []}
    checked_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for slot, key in enumerate(keys, start=1):
        r = await _account_for(key)
        r.update({"slot": slot, "label": "Main key" if slot == 1 else "Backup key", "checked_at": checked_at})
        rows.append(r)
    out = {"available": any(r["available"] for r in rows), "keys": rows, "checked_at": checked_at}
    first = rows[0]
    if first["available"]:
        out.update({k: first.get(k) for k in ("plan", "searches_per_month", "used_this_month", "left")})
    else:
        out["message"] = first.get("message")
    if out["available"]:
        _serp_cache = (time.time(), out)
    return out


# ---------------------------------------------------------------- the report
def _alert(level: str, title: str, detail: str) -> Dict[str, str]:
    return {"level": level, "title": title, "detail": detail}


def _pct_alert(alerts: List[Dict[str, str]], label: str, used: float, limit: float, unit: str, period: str) -> None:
    if not limit:
        return
    pct = used / limit * 100
    if pct >= 100:
        alerts.append(_alert("critical", f"{label}: limit reached", f"{used:,.0f}{unit} used of {limit:,.0f}{unit} {period} ({pct:.0f}%)."))
    elif pct >= 80:
        alerts.append(_alert("warning", f"{label}: close to the limit", f"{used:,.0f}{unit} used of {limit:,.0f}{unit} {period} ({pct:.0f}%)."))


async def build_usage(db: AsyncSession, start: date, end: date) -> Dict[str, Any]:
    await usage_recorder.flush()                                  # include calls that are still in memory
    limits = await get_limits(db)
    prices = await get_prices(db)
    now_day = today()
    month_start = now_day.replace(day=1)
    window_start = min(start, month_start, now_day - timedelta(days=14))
    rows = (await db.execute(
        select(ApiUsageDaily).where(ApiUsageDaily.day >= window_start, ApiUsageDaily.day <= max(end, now_day))
    )).scalars().all()
    first_day = (await db.execute(select(func.min(ApiUsageDaily.day)))).scalar_one_or_none()

    in_range = [r for r in rows if start <= r.day <= end]
    ai = [r for r in in_range if r.provider == AI_PROVIDER]

    def n(rs, outcome=None):
        return sum(r.requests for r in rs if outcome is None or r.outcome == outcome)

    def agg(rs) -> Dict[str, Any]:
        req = n(rs)
        ok = n(rs, "ok")
        ms = sum(r.total_ms for r in rs)
        return {"requests": req, "ok": ok, "failed": req - ok, "avg_ms": round(ms / req) if req else 0,
                "max_ms": max([r.max_ms for r in rs], default=0), "tokens_in": sum(r.tokens_in for r in rs), "tokens_out": sum(r.tokens_out for r in rs)}

    # ---- AI by model
    by_model, unpriced = [], []
    total_cost, any_cost = 0.0, False
    for model in sorted({r.model for r in ai}):
        rs = [r for r in ai if r.model == model]
        a = agg(rs)
        c = cost_usd(model, a["tokens_in"], a["tokens_out"], prices)
        a.update({"model": model, "cost_usd": round(c, 6) if c is not None else None})
        if c is None:
            if a["tokens_in"] or a["tokens_out"]:
                unpriced.append(model)
        else:
            total_cost += c
            any_cost = True
        by_model.append(a)
    by_model.sort(key=lambda x: x["requests"], reverse=True)

    # ---- AI by feature (with the models used for it)
    by_feature = []
    for feat in sorted({r.feature for r in ai}):
        rs = [r for r in ai if r.feature == feat]
        a = agg(rs)
        a["feature"] = feat
        a["models"] = [{"model": m, "requests": n([r for r in rs if r.model == m]), "failed": n([r for r in rs if r.model == m], "error")}
                       for m in sorted({r.model for r in rs})]
        by_feature.append(a)
    by_feature.sort(key=lambda x: x["requests"], reverse=True)

    # ---- external providers
    today_rows = [r for r in rows if r.day == now_day]
    month_rows = [r for r in rows if r.day >= month_start]
    external = []
    limit_map = {"serpapi": ("serpapi_monthly_requests", "month"), "geoapify": ("geoapify_daily_requests", "day"),
                 "railradar": ("railradar_daily_requests", "day")}
    for prov in EXTERNAL:
        rs = [r for r in in_range if r.provider == prov]
        a = agg(rs)
        a["provider"], a["label"] = prov, PROVIDER_LABELS[prov]
        a["p95_ms"] = usage_recorder.p95_ms(prov)
        a["endpoints"] = [{"endpoint": e, "requests": n([r for r in rs if r.model == e]), "failed": n([r for r in rs if r.model == e], "error")}
                          for e in sorted({r.model for r in rs})]
        key, period = limit_map.get(prov, (None, None))
        a["limit"] = limits.get(key) or 0 if key else 0
        a["limit_period"] = period
        a["period_used"] = n([r for r in (month_rows if period == "month" else today_rows) if r.provider == prov]) if key else None
        external.append(a)

    # ---- trend
    series = []
    d = start
    while d <= end:
        day_rows = [r for r in in_range if r.day == d]
        a_rows = [r for r in day_rows if r.provider == AI_PROVIDER]
        cost = 0.0
        for r in a_rows:
            c = cost_usd(r.model, r.tokens_in, r.tokens_out, prices)
            cost += c or 0.0
        series.append({"label": d.strftime("%d %b"), "date": d.isoformat(), "ai_ok": n(a_rows, "ok"), "ai_failed": n(a_rows, "error"),
                       "external_ok": n([r for r in day_rows if r.provider != AI_PROVIDER], "ok"),
                       "external_failed": n([r for r in day_rows if r.provider != AI_PROVIDER], "error"), "cost_usd": round(cost, 6)})
        d += timedelta(days=1)

    s = agg(ai)
    ext_all = [r for r in in_range if r.provider != AI_PROVIDER]
    rate = limits["usd_to_inr"]
    summary = {
        "ai_requests": s["requests"], "ai_ok": s["ok"], "ai_failed": s["failed"],
        "success_rate": round(s["ok"] / s["requests"] * 100, 1) if s["requests"] else None,
        "avg_ms": s["avg_ms"], "p95_ms": usage_recorder.p95_ms(AI_PROVIDER), "tokens_in": s["tokens_in"], "tokens_out": s["tokens_out"],
        "est_cost_usd": round(total_cost, 4) if any_cost else None, "est_cost_inr": round(total_cost * rate, 2) if any_cost else None,
        "unpriced_models": unpriced, "external_requests": n(ext_all), "external_failed": n(ext_all, "error"),
    }

    # ---- limits and alerts (always about the REAL today / this month, whatever range is shown)
    alerts: List[Dict[str, str]] = []
    ai_today = [r for r in today_rows if r.provider == AI_PROVIDER]
    month_cost = sum((cost_usd(r.model, r.tokens_in, r.tokens_out, prices) or 0.0) for r in month_rows if r.provider == AI_PROVIDER)
    _pct_alert(alerts, "AI requests today", n(ai_today), limits["ai_daily_requests"], "", "per day")
    _pct_alert(alerts, "Estimated AI spend this month", month_cost, limits["ai_monthly_cost_usd"], " USD", "per month")
    for prov, (key, period) in limit_map.items():
        used = n([r for r in (month_rows if period == "month" else today_rows) if r.provider == prov])
        _pct_alert(alerts, PROVIDER_LABELS[prov], used, limits[key], "", f"per {period}")

    serp = _serp_cache[1] if _serp_cache[1] else None
    for k in (serp or {}).get("keys", []):
        if k.get("available") and k.get("searches_per_month") and k.get("left") is not None:
            left_pct = k["left"] / k["searches_per_month"] * 100
            msg = f"{k['label']}: {k['left']} of {k['searches_per_month']} searches left this month."
            if left_pct <= 5:
                alerts.append(_alert("critical", f"SerpApi {k['label'].lower()}: searches almost gone", msg))
            elif left_pct <= 20:
                alerts.append(_alert("warning", f"SerpApi {k['label'].lower()}: searches running low", msg))

    # which SerpApi key is serving searches right now
    key_state = serpapi_client.key_status()
    why = {"quota": "it ran out of searches", "rate": "it was rate limited", "invalid": "it was rejected"}
    if key_state:
        resting = [k for k in key_state if k["state"] == "resting"]
        if len(resting) == len(key_state):
            names = " and ".join(k["label"].lower() for k in key_state)
            alerts.append(_alert("critical", "SerpApi: no key is working" if len(key_state) > 1 else "SerpApi key is exhausted",
                                 f"The {names} {'are' if len(key_state) > 1 else 'is'} out of searches or rejected, so flight and hotel searches are failing. "
                                 "Add searches to a plan or replace a key."))
        elif key_state[0]["state"] == "resting" and len(key_state) > 1:
            m = key_state[0]
            alerts.append(_alert("warning", "SerpApi backup key is in use",
                                 f"The main key stopped working ({why.get(m['reason'], 'a problem')}), so searches now use the backup key. "
                                 f"The main key is tried again in about {m['resting_minutes']} min. Check your SerpApi plan."))
        elif any(k["state"] == "resting" for k in key_state[1:]):
            m = next(k for k in key_state[1:] if k["state"] == "resting")
            alerts.append(_alert("info", "SerpApi backup key is resting", f"The backup key stopped working ({why.get(m['reason'], 'a problem')}). The main key is serving searches."))
    # unusual traffic: today against the average of the previous days that have data
    prev: Dict[date, int] = defaultdict(int)
    for r in rows:
        if now_day - timedelta(days=14) <= r.day < now_day:
            prev[r.day] += r.requests
    total_today = n(today_rows)
    if len(prev) >= 3:
        avg = sum(prev.values()) / len(prev)
        if total_today >= 50 and avg > 0 and total_today >= avg * 3:
            lvl = "critical" if total_today >= avg * 6 else "warning"
            alerts.append(_alert(lvl, "Unusually high traffic today", f"{total_today:,} AI and API calls today, about {total_today / avg:.1f}x the recent daily average ({avg:,.0f})."))
    burst = limits["hourly_burst_requests"]
    last_hour = usage_recorder.calls_last_hour()
    if burst and last_hour >= burst:
        alerts.append(_alert("critical" if last_hour >= burst * 1.5 else "warning", "Traffic burst in the last hour", f"{last_hour:,} calls in the last hour (alert level {burst:,})."))

    err_limit = limits["error_rate_percent"]
    for prov in (AI_PROVIDER,) + EXTERNAL:
        rs = [r for r in today_rows if r.provider == prov]
        total, bad = n(rs), n(rs, "error")
        if total >= 10 and bad / total * 100 >= err_limit:
            alerts.append(_alert("critical" if bad / total >= 0.5 else "warning", f"{PROVIDER_LABELS[prov]}: many failures today", f"{bad} of {total} calls failed ({bad / total * 100:.0f}%)."))
    quota_hits = [f for f in usage_recorder.failures if f.get("status") == 429]
    if quota_hits:
        provs = ", ".join(sorted({PROVIDER_LABELS.get(f["provider"], f["provider"]) for f in quota_hits}))
        alerts.append(_alert("warning", "Provider rate or quota limit hit", f"{len(quota_hits)} recent call(s) were refused with HTTP 429 ({provs})."))
    if unpriced:
        alerts.append(_alert("info", "Some AI models have no price", "Add a price below to include these in the spend estimate: " + ", ".join(unpriced) + "."))
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: order[a["level"]])

    return {
        "start": start.isoformat(), "end": end.isoformat(), "tracking_started": first_day.isoformat() if first_day else None,
        "summary": summary, "by_model": by_model, "by_feature": by_feature, "external": external, "series": series,
        "recent_failures": list(usage_recorder.failures)[:40], "alerts": alerts,
        "limits": limits, "serpapi_account": serp, "serpapi_keys": key_state,
        "serpapi_switches": serpapi_client.switch_count,
        "today": {"requests": total_today, "ai_requests": n(ai_today), "last_hour": last_hour, "month_ai_cost_usd": round(month_cost, 4)},
    }
