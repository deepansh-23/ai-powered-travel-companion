"""Monthly itinerary limit for normal accounts.

The limit is an admin setting (`itinerary_monthly_limit`, 0 = no restriction). Admin accounts are never limited
and never counted. A month is a calendar month in UTC; the count restarts on the 1st.

How it works for one generation:
  1. `reserve()` checks the limit and adds one to the count in one step, so two quick clicks cannot both slip
     through the last slot.
  2. If generating then FAILS, `refund()` gives that one back, so a failed attempt never costs the traveller.

If the database cannot be reached the traveller is NOT blocked (the same "fail open" rule as the other admin
settings): a broken counter must never stop someone from planning a trip.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import db_status, session_scope
from app.db_models import ItineraryUsage

logger = logging.getLogger(__name__)

SETTING_KEY = "itinerary_monthly_limit"
MAX_LIMIT = 1000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def month_key(now: Optional[datetime] = None) -> str:
    n = now or _now()
    return f"{n.year:04d}-{n.month:02d}"


def next_reset(now: Optional[datetime] = None) -> datetime:
    n = now or _now()
    year, month = (n.year + 1, 1) if n.month == 12 else (n.year, n.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc)


def _pretty(d: datetime) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _is_admin(user: Any) -> bool:
    return bool(getattr(user, "is_admin", False))


async def get_limit() -> int:
    """The current limit (0 = no restriction). Uses the cached admin settings; 0 when they cannot be read."""
    from app.services.site_settings_guard import load_settings
    try:
        raw = (await load_settings()).get(SETTING_KEY, 0)
        return max(0, min(MAX_LIMIT, int(raw)))
    except Exception:
        return 0


async def _used(db, user_id: str, month: str) -> int:
    row = (await db.execute(select(ItineraryUsage.count).where(
        ItineraryUsage.user_id == user_id, ItineraryUsage.month == month))).scalar_one_or_none()
    return int(row or 0)


async def status_for(user: Any) -> Dict[str, Any]:
    """What the pages show: the limit, how many were used this month, how many are left."""
    now = _now()
    out: Dict[str, Any] = {
        "limit": 0, "used": 0, "remaining": None, "unlimited": True, "is_admin": _is_admin(user),
        "month": month_key(now), "resets_on": next_reset(now).date().isoformat(), "resets_on_text": _pretty(next_reset(now)),
    }
    if _is_admin(user):
        return out                                   # admin: no restriction, nothing counted
    limit = await get_limit()
    used = 0
    if db_status()["ready"]:
        try:
            async with session_scope() as db:
                used = await _used(db, user.id, out["month"])
        except Exception:
            logger.info("Itinerary usage could not be read; showing 0 used.")
    out.update(limit=limit, used=used, unlimited=limit == 0,
               remaining=None if limit == 0 else max(0, limit - used))
    return out


def _limit_message(limit: int, resets_text: str) -> str:
    plural = "itinerary" if limit == 1 else "itineraries"
    return (f"You have used all {limit} {plural} allowed this month. "
            f"Your limit resets on {resets_text}. Please come back then.")


async def reserve(user: Any) -> bool:
    """Take one itinerary from this month's allowance. Returns True when one was counted (so it can be refunded).

    Raises HTTP 429 with a readable message when the allowance is used up.
    """
    if _is_admin(user) or not db_status()["ready"]:
        return False
    limit = await get_limit()
    month = month_key()
    try:
        async with session_scope() as db:
            for _attempt in (1, 2):
                if await _used(db, user.id, month) == 0:
                    exists = (await db.execute(select(ItineraryUsage).where(
                        ItineraryUsage.user_id == user.id, ItineraryUsage.month == month))).scalar_one_or_none()
                    if exists is None:
                        db.add(ItineraryUsage(user_id=user.id, month=month, count=0, updated_at=_now()))
                        try:
                            await db.commit()
                        except IntegrityError:        # another request created the row first: fine
                            await db.rollback()
                cond = [ItineraryUsage.user_id == user.id, ItineraryUsage.month == month]
                if limit > 0:
                    cond.append(ItineraryUsage.count < limit)          # the check and the +1 in ONE statement
                res = await db.execute(update(ItineraryUsage).where(*cond).values(
                    count=ItineraryUsage.count + 1, updated_at=_now()))
                await db.commit()
                if res.rowcount:
                    return True
                if limit > 0 and await _used(db, user.id, month) >= limit:
                    break
            if limit == 0:
                return False                      # no limit set: never block, even if the counter misbehaved
    except HTTPException:
        raise
    except Exception:
        logger.exception("Itinerary limit check failed; letting the request through.")
        return False
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=_limit_message(limit, _pretty(next_reset())))


async def refund(user: Any, reserved: bool) -> None:
    """Give back the slot taken by reserve() when the itinerary could not be produced."""
    if not reserved:
        return
    try:
        async with session_scope() as db:
            await db.execute(update(ItineraryUsage).where(
                ItineraryUsage.user_id == user.id, ItineraryUsage.month == month_key(),
                ItineraryUsage.count > 0).values(count=ItineraryUsage.count - 1, updated_at=_now()))
            await db.commit()
    except Exception:
        logger.exception("Could not refund an itinerary slot.")
