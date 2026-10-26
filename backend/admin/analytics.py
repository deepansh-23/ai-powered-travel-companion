"""Analytics for the admin dashboard, built from the small usage counters (see activity_service)."""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import ActivityDaily, User
from app.services.activity_service import FEATURES

MAX_RANGE_DAYS = 366
FEATURE_LABELS = {"itinerary": "Itinerary Planner", "area": "Area Guide", "cafes": "Quiet Work Cafés",
                  "medical": "24/7 Medical Care", "places": "Places Near You"}


def _bucket_start(d: date, interval: str) -> date:
    if interval == "week":
        return d - timedelta(days=d.weekday())          # Monday
    if interval == "month":
        return d.replace(day=1)
    return d


def _next_bucket(d: date, interval: str) -> date:
    if interval == "week":
        return d + timedelta(days=7)
    if interval == "month":
        return (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return d + timedelta(days=1)


def _label(d: date, interval: str) -> str:
    if interval == "month":
        return d.strftime("%b %Y")
    if interval == "week":
        return "Wk " + d.strftime("%d %b")
    return d.strftime("%d %b")


def parse_range(start: Optional[str], end: Optional[str], days: int, today: date) -> tuple:
    """(start, end) as dates, validated. Raises ValueError with a message the admin can read."""
    try:
        e = date.fromisoformat(end) if end else today
        s = date.fromisoformat(start) if start else e - timedelta(days=max(1, days) - 1)
    except ValueError:
        raise ValueError("Dates must look like 2026-10-31.")
    e = min(e, today)
    if s > e:
        raise ValueError("The start date must not be after the end date.")
    if (e - s).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"Choose a range of at most {MAX_RANGE_DAYS} days.")
    return s, e


async def build_analytics(db: AsyncSession, start: date, end: date, interval: str = "day") -> Dict[str, Any]:
    interval = interval if interval in ("day", "week", "month") else "day"
    window_start = min(start, end - timedelta(days=29))          # also needed for the 30-day "monthly" number

    rows = (await db.execute(
        select(ActivityDaily.day, ActivityDaily.actor_id, ActivityDaily.kind, ActivityDaily.feature, ActivityDaily.count)
        .where(ActivityDaily.day >= window_start, ActivityDaily.day <= end)
    )).all()
    first_day = (await db.execute(select(func.min(ActivityDaily.day)))).scalar_one_or_none()

    def actors(frm: date, to: date, kind: Optional[str] = None) -> Set[str]:
        return {r.actor_id for r in rows if frm <= r.day <= to and (kind is None or r.kind == kind)}

    # --- headline numbers, measured up to the end of the chosen range
    summary = {
        "dau": len(actors(end, end)), "wau": len(actors(end - timedelta(days=6), end)), "mau": len(actors(end - timedelta(days=29), end)),
        "dau_registered": len(actors(end, end, "registered")), "wau_registered": len(actors(end - timedelta(days=6), end, "registered")),
        "mau_registered": len(actors(end - timedelta(days=29), end, "registered")),
        "dau_guest": len(actors(end, end, "guest")), "wau_guest": len(actors(end - timedelta(days=6), end, "guest")),
        "mau_guest": len(actors(end - timedelta(days=29), end, "guest")),
    }

    in_range = [r for r in rows if start <= r.day <= end]
    reg_ids = {r.actor_id for r in in_range if r.kind == "registered"}
    created: Dict[str, datetime] = {}
    if reg_ids:
        ids = list(reg_ids)
        for i in range(0, len(ids), 500):
            for uid, created_at in (await db.execute(select(User.id, User.created_at).where(User.id.in_(ids[i:i + 500])))).all():
                created[uid] = created_at

    def created_date(uid: str) -> Optional[date]:
        c = created.get(uid)
        if c is None:
            return None
        return (c if c.tzinfo else c.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date()

    new_users = (await db.execute(
        select(User.created_at).where(User.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
                                      User.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    )).scalars().all()
    new_dates = [(c if c.tzinfo else c.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).date() for c in new_users]

    # --- trend buckets
    buckets: List[date] = []
    b = _bucket_start(start, interval)
    while b <= end:
        buckets.append(b)
        b = _next_bucket(b, interval)
    idx = {b: i for i, b in enumerate(buckets)}
    series = [{"label": _label(b, interval), "start": b.isoformat(), "active_registered": 0, "active_guest": 0,
               "new_registrations": 0, "returning_users": 0, "features": {f: 0 for f in FEATURES}} for b in buckets]
    reg_by_bucket: Dict[int, Set[str]] = defaultdict(set)
    guest_by_bucket: Dict[int, Set[str]] = defaultdict(set)
    for r in in_range:
        i = idx[_bucket_start(r.day, interval)]
        (reg_by_bucket if r.kind == "registered" else guest_by_bucket)[i].add(r.actor_id)
        if r.feature in FEATURES:
            series[i]["features"][r.feature] += r.count
    for i, s in enumerate(series):
        s["active_registered"] = len(reg_by_bucket[i])
        s["active_guest"] = len(guest_by_bucket[i])
        bstart = buckets[i]
        s["returning_users"] = sum(1 for uid in reg_by_bucket[i] if (created_date(uid) or date.min) < bstart)
    for d in new_dates:
        series[idx[_bucket_start(d, interval)]]["new_registrations"] += 1

    # --- features: registered vs guest
    features = []
    for f in FEATURES:
        reg = sum(r.count for r in in_range if r.feature == f and r.kind == "registered")
        guest = sum(r.count for r in in_range if r.feature == f and r.kind == "guest")
        features.append({"key": f, "label": FEATURE_LABELS[f], "registered": reg, "guest": guest, "total": reg + guest})
    features.sort(key=lambda x: x["total"], reverse=True)

    guest_ids = {r.actor_id for r in in_range if r.kind == "guest"}
    returning = sum(1 for uid in reg_ids if (created_date(uid) or date.min) < start)
    return {
        "start": start.isoformat(), "end": end.isoformat(), "interval": interval,
        "tracking_started": first_day.isoformat() if first_day else None,
        "summary": summary,
        "range_totals": {
            "active_registered": len(reg_ids), "active_guest": len(guest_ids),
            "new_registrations": len(new_dates), "returning_users": returning,
            "new_active_users": len(reg_ids) - returning,
            "feature_uses": sum(f["total"] for f in features),
        },
        "series": series,
        "features": features,
    }
