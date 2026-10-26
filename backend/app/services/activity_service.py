"""Collects anonymous usage counters for the admin Analytics page.

What is counted: a page visit (GET /api/auth/me) and each real use of a feature (one search / generation).
Who: a logged-in user id, or a guest (a random id from the guest cookie). Nothing else is stored.

Counts are kept in memory and written to the database in small batches, so a busy site is not slowed down.
Everything fails quietly: analytics must never break the site.
"""

import asyncio
import hashlib
import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from sqlalchemy import delete, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.db import db_status, session_scope
from app.db_models import ActivityDaily, AuthSession

logger = logging.getLogger(__name__)

FEATURES = ("itinerary", "area", "cafes", "medical", "places")
TRACKED = {
    ("GET", "/api/auth/me"): "visit",
    ("POST", "/api/itinerary/generate"): "itinerary",
    ("POST", "/api/area/summarize"): "area",
    ("POST", "/api/cafes/search"): "cafes",
    ("POST", "/api/medical/search"): "medical",
    ("POST", "/api/places/search"): "places",
}
FLUSH_SECONDS = 20
RETENTION_DAYS = 400
MAX_BUFFER_KEYS = 20000


def today() -> date:
    return datetime.now(timezone.utc).date()


class ActivityTracker:
    def __init__(self) -> None:
        self._buffer: Dict[Tuple[date, str, str], list] = {}      # (day, actor, feature) -> [kind, count]
        self._task: Optional[asyncio.Task] = None
        self._session_cache: Dict[str, Tuple[Optional[str], float]] = {}   # token hash -> (user id, expires)
        self._last_prune = 0.0

    # ------------------------------------------------------------ recording
    def record(self, actor_id: str, kind: str, feature: str, day: Optional[date] = None) -> None:
        key = (day or today(), actor_id, feature)
        row = self._buffer.get(key)
        if row is None:
            if len(self._buffer) >= MAX_BUFFER_KEYS:
                return                                            # bounded memory: drop rather than grow
            self._buffer[key] = [kind, 1]
        else:
            row[1] += 1

    async def _user_id_for_session(self, raw: str) -> Optional[str]:
        from app.services.auth_service import hash_token
        h = hash_token(raw)
        cached = self._session_cache.get(h)
        now = time.time()
        if cached and cached[1] > now:
            return cached[0]
        user_id: Optional[str] = None
        try:
            async with session_scope() as db:
                row = (await db.execute(
                    select(AuthSession.user_id).where(AuthSession.token_hash == h, AuthSession.expires_at > datetime.now(timezone.utc))
                )).first()
                user_id = row[0] if row else None
        except Exception:
            return None
        if len(self._session_cache) > 5000:
            self._session_cache.clear()
        self._session_cache[h] = (user_id, now + 300)
        return user_id

    async def actor_for(self, request: Request) -> Optional[Tuple[str, str]]:
        """('registered', user id) or ('guest', anonymous id). None when nobody can be told apart."""
        raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
        if raw and db_status()["ready"]:
            uid = await self._user_id_for_session(raw)
            if uid:
                return "registered", uid
        guest = request.cookies.get(settings.GUEST_COOKIE_NAME)
        if guest and guest.count(".") == 2:
            from app.security import is_valid_guest_token
            if is_valid_guest_token(guest):
                return "guest", "g" + guest.split(".")[1][:20]
        return None

    # ------------------------------------------------------------ saving
    async def flush(self) -> None:
        if not self._buffer or not db_status()["ready"]:
            return
        pending, self._buffer = self._buffer, {}
        try:
            async with session_scope() as db:
                for (day, actor, feature), (kind, n) in pending.items():
                    row = await db.get(ActivityDaily, (day, actor, feature))
                    if row is None:
                        db.add(ActivityDaily(day=day, actor_id=actor, feature=feature, kind=kind, count=n))
                    else:
                        row.count = (row.count or 0) + n
                await db.commit()
        except Exception as exc:
            logger.warning("Could not save activity counters (will retry): %s", exc)
            for key, (kind, n) in pending.items():                # keep them for the next attempt
                cur = self._buffer.get(key)
                if cur is None:
                    if len(self._buffer) < MAX_BUFFER_KEYS:
                        self._buffer[key] = [kind, n]
                else:
                    cur[1] += n

    async def prune(self) -> None:
        try:
            async with session_scope() as db:
                await db.execute(delete(ActivityDaily).where(ActivityDaily.day < today() - timedelta(days=RETENTION_DAYS)))
                await db.commit()
        except Exception as exc:
            logger.info("Activity prune skipped: %s", exc)

    # ------------------------------------------------------------ background loop
    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            await self.flush()
            if time.time() - self._last_prune > 86400:
                self._last_prune = time.time()
                await self.prune()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        await self.flush()


activity_tracker = ActivityTracker()


class ActivityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from app.services.usage_service import current_feature, feature_for_path
        current_feature.set(feature_for_path(request.url.path))     # lets AI / API calls be attributed to a feature
        response = await call_next(request)
        try:
            feature = TRACKED.get((request.method, request.url.path))
            if feature and response.status_code < 400:
                actor = await activity_tracker.actor_for(request)
                if actor:
                    kind, actor_id = actor
                    activity_tracker.record(actor_id, kind, feature)
        except Exception:
            logger.debug("activity tracking skipped", exc_info=True)
        return response
