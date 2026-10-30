"""Admin service layer — database queries for admin endpoints.

All queries use safe ORM operations. No raw SQL interpolation.
Password hashes, tokens and internal secrets are never returned.
"""

import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import (
    AccountDeletionRequest, AppSetting, AuthSession, Feedback, History, LoginAttempt, SavedSession, User,
)


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


def _last_active_subquery():
    """Latest time any of the user's browsers was seen (sessions refresh this about every 5 minutes)."""
    return (
        select(AuthSession.user_id.label("uid"), func.max(AuthSession.last_seen_at).label("last_seen"))
        .group_by(AuthSession.user_id)
        .subquery()
    )


def _user_row(u: User, last_seen, counts: dict, pending: dict) -> dict:
    last_active = _as_utc(last_seen) or _as_utc(u.last_login_at)
    login = _as_utc(u.last_login_at)
    if last_active and login and login > last_active:
        last_active = login
    req = pending.get(u.id)
    return {
        "id": u.id,
        "username": u.username,
        "is_active": u.is_active,
        "is_admin": bool(getattr(u, "is_admin", False)),
        "created_at": _as_utc(u.created_at),
        "last_login_at": login,
        "last_active_at": last_active,
        "itinerary_count": counts.get(u.id, 0),
        "deletion_requested": req is not None,
        "deletion_requested_at": _as_utc(req.requested_at) if req else None,
        "deletion_reason": req.reason if req else None,
    }


async def _pending_requests(db: AsyncSession, user_ids: list) -> dict:
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(AccountDeletionRequest).where(AccountDeletionRequest.user_id.in_(user_ids), AccountDeletionRequest.status == "pending")
    )).scalars().all()
    return {r.user_id: r for r in rows}


async def list_users(
    db: AsyncSession,
    page: int = 1,
    search: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = None,
) -> Tuple[list, int]:
    """Return (user_rows, total_count) for the given page.

    status: 'active' | 'suspended' | 'deletion_requested'.  sort: newest (default) | oldest | last_active | username.
    """
    last = _last_active_subquery()
    q = select(User, last.c.last_seen).outerjoin(last, last.c.uid == User.id)

    if search:
        term = f"%{search.strip().lower()}%"
        q = q.where(User.username_lower.like(term))

    if role == "admin":
        q = q.where(User.is_admin.is_(True))
    elif role == "user":
        q = q.where(or_(User.is_admin.is_(False), User.is_admin.is_(None)))

    if status == "active":
        q = q.where(User.is_active.is_(True))
    elif status == "suspended":
        q = q.where(User.is_active.is_(False))
    elif status == "deletion_requested":
        q = q.where(User.id.in_(select(AccountDeletionRequest.user_id).where(AccountDeletionRequest.status == "pending")))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    order = {
        "oldest": [User.created_at.asc()],
        "username": [User.username_lower.asc()],
        "last_active": [func.coalesce(last.c.last_seen, User.last_login_at).desc().nulls_last(), User.created_at.desc()],
    }.get((sort or "").lower(), [User.created_at.desc()])
    offset = (max(page, 1) - 1) * PAGE_SIZE
    rows = (await db.execute(q.order_by(*order).offset(offset).limit(PAGE_SIZE))).all()

    user_ids = [u.id for u, _ in rows]
    counts: dict = {}
    if user_ids:
        cnt_rows = (await db.execute(
            select(History.user_id, func.count()).where(History.user_id.in_(user_ids)).group_by(History.user_id)
        )).all()
        counts = {r[0]: r[1] for r in cnt_rows}
    pending = await _pending_requests(db, user_ids)

    return [_user_row(u, ls, counts, pending) for u, ls in rows], total


async def get_user(db: AsyncSession, user_id: str) -> Optional[dict]:
    last = _last_active_subquery()
    row = (await db.execute(
        select(User, last.c.last_seen).outerjoin(last, last.c.uid == User.id).where(User.id == user_id)
    )).first()
    if row is None:
        return None
    u, last_seen = row
    cnt = (await db.execute(
        select(func.count()).select_from(History).where(History.user_id == user_id)
    )).scalar_one()
    pending = await _pending_requests(db, [user_id])
    return _user_row(u, last_seen, {user_id: cnt}, pending)


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
    await db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == target_id))
    # Detach reviews (set user_id to NULL to preserve them anonymously)
    await db.execute(update(Feedback).where(Feedback.user_id == target_id).values(user_id=None))
    await db.execute(delete(History).where(History.user_id == target_id))
    await db.execute(delete(SavedSession).where(SavedSession.user_id == target_id))
    await db.execute(delete(AuthSession).where(AuthSession.user_id == target_id))
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_lower == uname))
    await db.execute(delete(User).where(User.id == target_id))
    await db.commit()


# ──────────────────────────── Password reset + deletion requests ──────────────

_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _temporary_password(username: str) -> str:
    from app.services import auth_service
    for _ in range(20):
        pw = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(14))
        try:
            auth_service.validate_password(pw, username)
            return pw
        except auth_service.ValidationFailed:
            continue
    raise RuntimeError("Could not generate a temporary password.")


async def reset_user_password(db: AsyncSession, target_id: str, acting_admin_id: str) -> str:
    """Sets a new random password, signs the user out everywhere and returns it (shown to the admin once)."""
    from app.services import auth_service
    target = (await db.execute(select(User).where(User.id == target_id))).scalar_one_or_none()
    if target is None:
        raise LookupError("User not found.")
    if target_id == acting_admin_id:
        raise ValueError("Use the normal change-password option for your own account.")
    if getattr(target, "is_admin", False):
        raise ValueError("Admin passwords cannot be reset here. Remove the admin role first, or ask the admin to use account recovery.")
    temp = _temporary_password(target.username)
    target.password_hash = auth_service._hasher.hash(temp)
    await db.execute(delete(AuthSession).where(AuthSession.user_id == target_id))
    await db.execute(delete(LoginAttempt).where(LoginAttempt.username_lower == target.username_lower))
    await db.commit()
    return temp


async def list_deletion_requests(db: AsyncSession) -> list:
    last = _last_active_subquery()
    rows = (await db.execute(
        select(AccountDeletionRequest, User, last.c.last_seen)
        .join(User, User.id == AccountDeletionRequest.user_id)
        .outerjoin(last, last.c.uid == User.id)
        .where(AccountDeletionRequest.status == "pending")
        .order_by(AccountDeletionRequest.requested_at.asc())
    )).all()
    return [{
        "id": r.id, "user_id": u.id, "username": u.username, "reason": r.reason or "",
        "requested_at": _as_utc(r.requested_at), "registered_at": _as_utc(u.created_at),
        "last_active_at": _as_utc(ls) or _as_utc(u.last_login_at), "is_admin": bool(getattr(u, "is_admin", False)),
    } for r, u, ls in rows]


async def approve_deletion_request(db: AsyncSession, request_id: str, acting_admin_id: str) -> None:
    req = (await db.execute(select(AccountDeletionRequest).where(AccountDeletionRequest.id == request_id))).scalar_one_or_none()
    if req is None or req.status != "pending":
        raise LookupError("Deletion request not found.")
    await delete_user(db, req.user_id, acting_admin_id)      # same safety guards as a normal delete


async def dismiss_deletion_request(db: AsyncSession, request_id: str) -> None:
    req = (await db.execute(select(AccountDeletionRequest).where(AccountDeletionRequest.id == request_id))).scalar_one_or_none()
    if req is None or req.status != "pending":
        raise LookupError("Deletion request not found.")
    await db.delete(req)                                      # the user may ask again later
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


# ──────────────────────────── Settings ──────────────────────────────────────

# Allow-list of editable settings: key -> (default, description). Nothing else can be stored,
# so API keys / DB credentials can never be written or read through this endpoint.
SETTING_DEFAULTS = {
    "maintenance_mode": ("false", "Pause public access while retaining admin access"),
    "public_notice_enabled": ("false", "Display top announcement banner on travel site"),
    "public_notice_text": ("", "Text of announcement banner"),
    "guest_mode_enabled": ("true", "Allow unauthenticated visitors to use planner as guest"),
    "allow_registration": ("true", "Allow new users to create accounts"),
    "allow_reviews": ("true", "Allow logged-in users to submit new reviews"),
    "itinerary_monthly_limit": ("0", "Itineraries a normal account can generate per month (0 = no restriction)"),
}
BOOL_SETTINGS = {k for k, (d, _) in SETTING_DEFAULTS.items() if d in ("true", "false")}
# Turning these OFF/ON is visible to every visitor, so the admin must confirm explicitly.
DISRUPTIVE_VALUES = {
    "maintenance_mode": True,
    "allow_registration": False,
    "guest_mode_enabled": False,
    "allow_reviews": False,
}
NOTICE_MAX_LEN = 300
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


ITINERARY_LIMIT_MAX = 1000


def _limit(d: dict) -> int:
    """Monthly itinerary limit as a whole number (0 = no restriction); a damaged value counts as 0."""
    try:
        return max(0, min(ITINERARY_LIMIT_MAX, int(float(str(d.get("itinerary_monthly_limit", "0")).strip() or 0))))
    except (TypeError, ValueError):
        return 0


def _bool(d: dict, key: str) -> bool:
    return str(d.get(key, SETTING_DEFAULTS[key][0])).strip().lower() == "true"


async def get_settings(db: AsyncSession) -> dict:
    rows = (await db.execute(select(AppSetting))).scalars().all()
    d = {r.key: r.value for r in rows if r.key in SETTING_DEFAULTS}
    latest_update = max([_as_utc(r.updated_at) for r in rows if r.updated_at], default=None)

    return {
        "maintenance_mode": _bool(d, "maintenance_mode"),
        "public_notice_enabled": _bool(d, "public_notice_enabled"),
        "public_notice_text": d.get("public_notice_text", ""),
        "guest_mode_enabled": _bool(d, "guest_mode_enabled"),
        "allow_registration": _bool(d, "allow_registration"),
        "allow_reviews": _bool(d, "allow_reviews"),
        "itinerary_monthly_limit": _limit(d),
        "updated_at": latest_update,
    }


def clean_notice_text(text: Optional[str]) -> str:
    """Plain text only: strip control characters, collapse whitespace, cap the length."""
    cleaned = _CONTROL_CHARS.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:NOTICE_MAX_LEN]


def disruptive_changes(current: dict, new_settings: dict) -> list:
    """Names of settings in `new_settings` that would newly apply a disruptive value."""
    out = []
    for key, bad_value in DISRUPTIVE_VALUES.items():
        if key in new_settings and new_settings[key] is not None:
            if bool(new_settings[key]) == bad_value and bool(current.get(key)) != bad_value:
                out.append(key)
    return out


async def update_settings(db: AsyncSession, new_settings: dict) -> dict:
    """Validate and upsert allow-listed settings. Raises ValueError on invalid input."""
    unknown = [k for k in new_settings if k not in SETTING_DEFAULTS]
    if unknown:
        raise ValueError("Unknown setting: " + ", ".join(sorted(unknown)))

    values = dict(new_settings)
    if values.get("public_notice_text") is not None:
        values["public_notice_text"] = clean_notice_text(values["public_notice_text"])

    current = await get_settings(db)
    final_enabled = values.get("public_notice_enabled", current["public_notice_enabled"])
    final_text = values.get("public_notice_text", current["public_notice_text"])
    if final_enabled and not (final_text or "").strip():
        raise ValueError("Enter the announcement text before enabling the public notice.")

    now = _utcnow()
    for key, raw in values.items():
        if raw is None:
            continue
        if key in BOOL_SETTINGS:
            if not isinstance(raw, bool):
                raise ValueError(f"{key} must be true or false.")
            str_val = "true" if raw else "false"
        elif key == "itinerary_monthly_limit":
            if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= ITINERARY_LIMIT_MAX:
                raise ValueError(f"The monthly itinerary limit must be a whole number from 0 (no restriction) to {ITINERARY_LIMIT_MAX}.")
            str_val = str(raw)
        else:
            str_val = str(raw)
        row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
        if row is not None:
            row.value = str_val
            row.updated_at = now
        else:
            db.add(AppSetting(key=key, value=str_val, description=SETTING_DEFAULTS[key][1], updated_at=now))
    await db.commit()
    invalidate_settings_cache()
    return await get_settings(db)


_settings_cache: Optional[dict] = None
_settings_cache_time: float = 0.0


async def get_cached_settings(db: AsyncSession, max_age: float = 5.0) -> dict:
    global _settings_cache, _settings_cache_time
    import time as _t
    now = _t.time()
    if _settings_cache is not None and (now - _settings_cache_time) < max_age:
        return _settings_cache
    _settings_cache = await get_settings(db)
    _settings_cache_time = now
    return _settings_cache


def peek_cached_settings(max_age: float = 5.0) -> Optional[dict]:
    """Return fresh cached settings without touching the database, else None."""
    import time as _t
    if _settings_cache is not None and (_t.time() - _settings_cache_time) < max_age:
        return _settings_cache
    return None


def invalidate_settings_cache() -> None:
    global _settings_cache
    _settings_cache = None


# ──────────────────────────── Feedback Management ───────────────────────────

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{8,}\d(?!\w)")
_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


def redact_pii(text: Optional[str]) -> str:
    """Mask emails, phone numbers and long token-like strings in free text shown to admins."""
    out = text or ""
    out = _EMAIL_RE.sub("[email hidden]", out)
    out = _PHONE_RE.sub("[phone hidden]", out)
    out = _TOKEN_RE.sub("[secret hidden]", out)
    return out


def _feedback_row(f, username) -> dict:
    return {
        "id": f.id,
        "username": username,
        "rating": f.rating,
        "comment": redact_pii(f.comment),
        "service_used": f.service_used,
        "status": getattr(f, "status", "pending") or "pending",
        "admin_notes": getattr(f, "admin_notes", None),
        "created_at": _as_utc(f.created_at),
    }



async def list_admin_feedback(
    db: AsyncSession,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    search: Optional[str] = None,
    service_used: Optional[str] = None,
    status: Optional[str] = None,
    rating: Optional[int] = None,
) -> Tuple[list, int, dict]:
    q = select(Feedback, User.username).outerjoin(User, User.id == Feedback.user_id)

    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(Feedback.comment).like(s),
            func.lower(Feedback.service_used).like(s),
            func.lower(User.username).like(s),
        ))

    if service_used and service_used.strip().lower() not in ("all", ""):
        q = q.where(Feedback.service_used == service_used.strip())

    if status and status.strip().lower() not in ("all", ""):
        wanted = status.strip().lower()
        if wanted == "pending":
            q = q.where(or_(Feedback.status == "pending", Feedback.status.is_(None)))
        else:
            q = q.where(Feedback.status == wanted)

    if rating and 1 <= rating <= 5:
        q = q.where(Feedback.rating == rating)

    # Total matching
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Pagination & sorting (newest first)
    offset = (page - 1) * page_size
    q = q.order_by(Feedback.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(q)).all()

    items = [_feedback_row(f, uname) for f, uname in rows]

    # Summary statistics across all feedback
    total_all = (await db.execute(select(func.count()).select_from(Feedback))).scalar_one()
    pending = (await db.execute(select(func.count()).select_from(Feedback).where(or_(Feedback.status == "pending", Feedback.status.is_(None))))).scalar_one()
    reviewed = (await db.execute(select(func.count()).select_from(Feedback).where(Feedback.status == "reviewed"))).scalar_one()
    resolved = (await db.execute(select(func.count()).select_from(Feedback).where(Feedback.status == "resolved"))).scalar_one()
    avg_rating_val = (await db.execute(select(func.avg(Feedback.rating)).select_from(Feedback))).scalar()
    avg_rating = round(float(avg_rating_val), 1) if avg_rating_val is not None else 0.0

    summary = {
        "total": total_all,
        "pending": pending,
        "reviewed": reviewed,
        "resolved": resolved,
        "avg_rating": avg_rating,
    }

    return items, total, summary


async def get_admin_feedback(db: AsyncSession, feedback_id: str) -> Optional[dict]:
    row = (await db.execute(
        select(Feedback, User.username).outerjoin(User, User.id == Feedback.user_id).where(Feedback.id == feedback_id)
    )).first()
    if row is None:
        return None
    f, username = row
    return _feedback_row(f, username)


async def patch_admin_feedback(
    db: AsyncSession,
    feedback_id: str,
    status: Optional[str] = None,
    admin_notes: Optional[str] = None,
) -> dict:
    f = (await db.execute(select(Feedback).where(Feedback.id == feedback_id))).scalar_one_or_none()
    if f is None:
        raise LookupError("Feedback record not found.")

    if status is not None:
        status = status.strip().lower()
        if status not in ("pending", "reviewed", "resolved"):
            raise ValueError("Status must be pending, reviewed or resolved.")
        f.status = status
    if admin_notes is not None:
        f.admin_notes = admin_notes.strip()

    await db.commit()
    await db.refresh(f)
    return await get_admin_feedback(db, feedback_id)


async def delete_admin_feedback(db: AsyncSession, feedback_id: str) -> None:
    f = (await db.execute(select(Feedback).where(Feedback.id == feedback_id))).scalar_one_or_none()
    if f is None:
        raise LookupError("Feedback record not found.")
    await db.execute(delete(Feedback).where(Feedback.id == feedback_id))
    await db.commit()

