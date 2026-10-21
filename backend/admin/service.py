"""Admin service layer — database queries for admin endpoints.

All queries use safe ORM operations. No raw SQL interpolation.
Password hashes, tokens and internal secrets are never returned.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import AuthSession, Feedback, History, LoginAttempt, SavedSession, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ──────────────────────────── Overview ──────────────────────────────────────

async def get_overview(db: AsyncSession) -> dict:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_admins = (await db.execute(select(func.count()).select_from(User).where(User.is_admin.is_(True)))).scalar_one()
    active_users = (await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))).scalar_one()
    inactive_users = total_users - active_users

    total_itineraries = (await db.execute(select(func.count()).select_from(History))).scalar_one()

    since_7d = _utcnow() - timedelta(days=7)
    recent_regs = (await db.execute(
        select(func.count()).select_from(User).where(User.created_at >= since_7d)
    )).scalar_one()

    return {
        "total_users": total_users,
        "total_admins": total_admins,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "total_itineraries": total_itineraries,
        "registrations_last_7_days": recent_regs,
        "database_healthy": True,
        "db_error": None,
    }


# ──────────────────────────── Users ─────────────────────────────────────────

PAGE_SIZE = 20


async def list_users(
    db: AsyncSession,
    page: int = 1,
    search: Optional[str] = None,
    role: Optional[str] = None,
) -> Tuple[list, int]:
    """Return (user_rows, total_count) for the given page."""
    q = select(User)

    if search:
        term = f"%{search.strip().lower()}%"
        q = q.where(User.username_lower.like(term))

    if role == "admin":
        q = q.where(User.is_admin.is_(True))
    elif role == "user":
        q = q.where(or_(User.is_admin.is_(False), User.is_admin.is_(None)))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (max(page, 1) - 1) * PAGE_SIZE
    rows = (await db.execute(
        q.order_by(User.created_at.desc()).offset(offset).limit(PAGE_SIZE)
    )).scalars().all()

    # Fetch itinerary counts per user
    user_ids = [u.id for u in rows]
    counts: dict = {}
    if user_ids:
        cnt_rows = (await db.execute(
            select(History.user_id, func.count()).where(History.user_id.in_(user_ids)).group_by(History.user_id)
        )).all()
        counts = {r[0]: r[1] for r in cnt_rows}

    result = []
    for u in rows:
        result.append({
            "id": u.id,
            "username": u.username,
            "is_active": u.is_active,
            "is_admin": bool(getattr(u, "is_admin", False)),
            "created_at": _as_utc(u.created_at),
            "last_login_at": _as_utc(u.last_login_at),
            "itinerary_count": counts.get(u.id, 0),
        })

    return result, total


async def get_user(db: AsyncSession, user_id: str) -> Optional[dict]:
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None:
        return None
    cnt = (await db.execute(
        select(func.count()).select_from(History).where(History.user_id == user_id)
    )).scalar_one()
    return {
        "id": u.id,
        "username": u.username,
        "is_active": u.is_active,
        "is_admin": bool(getattr(u, "is_admin", False)),
        "created_at": _as_utc(u.created_at),
        "last_login_at": _as_utc(u.last_login_at),
        "itinerary_count": cnt,
    }


async def count_admins(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count()).select_from(User).where(User.is_admin.is_(True))
    )).scalar_one()


async def patch_user(
    db: AsyncSession,
    target_id: str,
    acting_admin_id: str,
    is_active: Optional[bool],
    is_admin: Optional[bool],
) -> dict:
    """Update is_active / is_admin with safety guards.

    Raises ValueError for unsafe operations.
    """
    target = (await db.execute(select(User).where(User.id == target_id))).scalar_one_or_none()
    if target is None:
        raise LookupError("User not found.")

    if target_id == acting_admin_id:
        if is_active is False:
            raise ValueError("You cannot deactivate your own account.")
        if is_admin is False:
            raise ValueError("You cannot remove your own admin privileges.")

    # Prevent demoting the last admin
    if is_admin is False and getattr(target, "is_admin", False):
        remaining = await count_admins(db)
        if remaining <= 1:
            raise ValueError("Cannot demote the last admin account.")

    changes: dict = {}
    if is_active is not None:
        changes["is_active"] = is_active
    if is_admin is not None:
        changes["is_admin"] = is_admin

    if changes:
        await db.execute(update(User).where(User.id == target_id).values(**changes))
        # Invalidate sessions when deactivating
        if is_active is False:
            await db.execute(delete(AuthSession).where(AuthSession.user_id == target_id))
        await db.commit()

    result = await get_user(db, target_id)
    return result


async def delete_user(
    db: AsyncSession,
    target_id: str,
    acting_admin_id: str,
) -> None:
    """Safely delete a user account and related data."""
    if target_id == acting_admin_id:
        raise ValueError("You cannot delete your own admin account.")

    target = (await db.execute(select(User).where(User.id == target_id))).scalar_one_or_none()
    if target is None:
        raise LookupError("User not found.")

    if getattr(target, "is_admin", False):
        remaining = await count_admins(db)
        if remaining <= 1:
            raise ValueError("Cannot delete the last admin account.")

    uname = target.username_lower
    # Detach reviews (set user_id to NULL to preserve them anonymously)
    await db.execute(update(Feedback).where(Feedback.user_id == target_id).values(user_id=None))
    await db.execute(delete(History).where(History.user_id == target_id))
    await db.execute(delete(SavedSession).where(SavedSession.user_id == target_id))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == target_id))
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_lower == uname))
    await db.execute(delete(User).where(User.id == target_id))
    await db.commit()


# ──────────────────────────── Itineraries ───────────────────────────────────

async def list_itineraries(
    db: AsyncSession,
    page: int = 1,
    search: Optional[str] = None,
    feature_type: Optional[str] = None,
) -> Tuple[list, int]:
    q = select(History, User.username).outerjoin(User, User.id == History.user_id)

    if search:
        term = f"%{search.strip()}%"
        q = q.where(or_(
            History.title.ilike(term),
            History.preview.ilike(term),
            User.username.ilike(term),
        ))

    if feature_type and feature_type.strip().lower() not in ("all", ""):
        q = q.where(History.feature_type == feature_type.strip().lower())

    count_q = select(func.count()).select_from(History)
    if search:
        term2 = f"%{search.strip()}%"
        count_q = count_q.join(User, User.id == History.user_id, isouter=True).where(
            or_(History.title.ilike(term2), History.preview.ilike(term2), User.username.ilike(term2))
        )
    if feature_type and feature_type.strip().lower() not in ("all", ""):
        count_q = count_q.where(History.feature_type == feature_type.strip().lower())

    total = (await db.execute(count_q)).scalar_one()

    offset = (max(page, 1) - 1) * PAGE_SIZE
    rows = (await db.execute(
        q.order_by(History.created_at.desc()).offset(offset).limit(PAGE_SIZE)
    )).all()

    result = []
    for h, username in rows:
        result.append({
            "id": h.id,
            "user_id": h.user_id,
            "username": username,
            "feature_type": h.feature_type,
            "title": h.title,
            "preview": h.preview or "",
            "created_at": _as_utc(h.created_at),
        })
    return result, total


async def get_itinerary(db: AsyncSession, itinerary_id: str) -> Optional[dict]:
    row = (await db.execute(
        select(History, User.username).outerjoin(User, User.id == History.user_id).where(History.id == itinerary_id)
    )).first()
    if row is None:
        return None
    h, username = row
    return {
        "id": h.id,
        "user_id": h.user_id,
        "username": username,
        "feature_type": h.feature_type,
        "title": h.title,
        "preview": h.preview or "",
        "created_at": _as_utc(h.created_at),
        "payload": h.payload or {},
    }


async def delete_itinerary(db: AsyncSession, itinerary_id: str) -> None:
    h = (await db.execute(select(History).where(History.id == itinerary_id))).scalar_one_or_none()
    if h is None:
        raise LookupError("Itinerary not found.")
    await db.execute(delete(History).where(History.id == itinerary_id))
    await db.commit()
