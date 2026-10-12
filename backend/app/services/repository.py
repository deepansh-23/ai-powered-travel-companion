"""PostgreSQL data access for per-user History and Reviews."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db_models import Feedback, History, SavedSession, User, utcnow

_TYPE_ALIASES = {"area_guide": "area", "quiet_cafes": "cafes", "medical_care": "medical"}


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:  # SQLite drops tzinfo; values are stored as UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="minutes")


def _history_dict(h: History) -> Dict[str, Any]:
    return {
        "id": h.id, "feature_type": h.feature_type, "title": h.title,
        "preview": h.preview or "", "payload": h.payload or {}, "created_at": _iso(h.created_at),
    }


async def list_history(db: AsyncSession, user_id: str, feature_type: Optional[str] = None) -> List[Dict[str, Any]]:
    q = select(History).where(History.user_id == user_id)
    if feature_type and feature_type.strip().lower() not in ("all", ""):
        target = feature_type.strip().lower()
        q = q.where(or_(History.feature_type == target, History.feature_type == _TYPE_ALIASES.get(target, target)))
    rows = (await db.execute(q.order_by(desc(History.created_at)))).scalars().all()
    return [_history_dict(h) for h in rows]


async def create_history(db: AsyncSession, user_id: str, feature_type: str, title: str,
                         preview: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    item = History(
        id=f"hist_{uuid.uuid4().hex[:12]}", user_id=user_id, feature_type=feature_type[:30],
        title=title[:300], preview=preview or "", payload=payload or {},
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _history_dict(item)


async def delete_history(db: AsyncSession, user_id: str, item_id: str) -> bool:
    result = await db.execute(delete(History).where(History.id == item_id, History.user_id == user_id))
    await db.commit()
    return (result.rowcount or 0) > 0


def _feedback_dict(f: Feedback, username: Optional[str]) -> Dict[str, Any]:
    return {
        "id": f.id, "rating": f.rating, "comment": f.comment, "service_used": f.service_used,
        "created_at": _iso(f.created_at), "username": username,
    }


async def list_feedback(db: AsyncSession) -> List[Dict[str, Any]]:
    q = select(Feedback, User.username).outerjoin(User, User.id == Feedback.user_id).order_by(desc(Feedback.created_at))
    return [_feedback_dict(f, name) for f, name in (await db.execute(q)).all()]


async def create_feedback(db: AsyncSession, user: User, rating: int, comment: str,
                          service_used: Optional[str]) -> Dict[str, Any]:
    if not (1 <= rating <= 5):
        raise ValueError("Rating must be an integer between 1 and 5.")
    if not comment or not comment.strip():
        raise ValueError("Comment cannot be empty.")
    item = Feedback(
        id=f"rev_{uuid.uuid4().hex[:12]}", user_id=user.id, rating=rating,
        comment=comment.strip(), service_used=(service_used or None),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _feedback_dict(item, user.username)


# ----------------------------------------------------------------- saved sessions (drafts)
SESSION_SERVICES = {"itinerary", "area", "places", "cafes", "medical"}
MAX_SESSIONS_PER_SERVICE = 10


class SessionLimitReached(Exception):
    pass


def _session_meta(r: SavedSession) -> Dict[str, Any]:
    return {"id": r.id, "service": r.service, "title": r.title,
            "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at)}


async def list_sessions(db: AsyncSession, user_id: str, service: Optional[str] = None) -> List[Dict[str, Any]]:
    q = select(SavedSession).where(SavedSession.user_id == user_id)
    if service:
        q = q.where(SavedSession.service == service)
    rows = (await db.execute(q.order_by(desc(SavedSession.updated_at)))).scalars().all()
    return [_session_meta(r) for r in rows]


async def get_session(db: AsyncSession, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    r = (await db.execute(select(SavedSession).where(
        SavedSession.id == session_id, SavedSession.user_id == user_id))).scalar_one_or_none()
    return None if r is None else {**_session_meta(r), "state": r.state or {}}


async def save_session(db: AsyncSession, user_id: str, service: str, title: str, state: Dict[str, Any],
                       session_id: Optional[str] = None) -> Dict[str, Any]:
    """Update the draft `session_id` if it is the caller's own, otherwise create a new one."""
    existing = None
    if session_id:
        existing = (await db.execute(select(SavedSession).where(
            SavedSession.id == session_id, SavedSession.user_id == user_id))).scalar_one_or_none()
    if existing is not None:
        existing.title, existing.state, existing.service = title[:300], state, service
        existing.updated_at = utcnow()
        await db.commit()
        await db.refresh(existing)
        return _session_meta(existing)

    count = len((await db.execute(select(SavedSession.id).where(
        SavedSession.user_id == user_id, SavedSession.service == service))).all())
    if count >= MAX_SESSIONS_PER_SERVICE:
        raise SessionLimitReached(
            f"You already have {MAX_SESSIONS_PER_SERVICE} saved sessions for this service. Delete one first.")
    row = SavedSession(id=f"sess_{uuid.uuid4().hex[:12]}", user_id=user_id, service=service,
                       title=title[:300], state=state)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _session_meta(row)


async def delete_session(db: AsyncSession, user_id: str, session_id: str) -> bool:
    result = await db.execute(delete(SavedSession).where(
        SavedSession.id == session_id, SavedSession.user_id == user_id))
    await db.commit()
    return (result.rowcount or 0) > 0
