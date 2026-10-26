"""Records every call to the AI model and to external APIs for the admin "AI & API Usage" monitor.

Stored: provider, model or endpoint, feature, success or failure, response time, token counts. Never stored:
prompts, answers, API keys, user ids, IP addresses. Error text is scrubbed of anything that looks like a secret.

Counts are batched in memory and written every few seconds; failing to record never affects a request.
"""

import asyncio
import contextlib
import contextvars
import logging
import re
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import Any, Deque, Dict, Iterator, Optional, Tuple

from sqlalchemy import delete

from app.db import db_status, session_scope
from app.db_models import ApiUsageDaily

logger = logging.getLogger(__name__)

AI_PROVIDER = "gemini"
FLUSH_SECONDS = 20
RETENTION_DAYS = 400
MAX_BUFFER_KEYS = 5000

current_feature: contextvars.ContextVar[str] = contextvars.ContextVar("usage_feature", default="other")

_FEATURE_PREFIXES = (
    ("/api/itinerary", "itinerary"), ("/api/transport", "itinerary"), ("/api/hotels", "itinerary"), ("/api/flights", "itinerary"),
    ("/api/area", "area"), ("/api/cafes", "cafes"), ("/api/medical", "medical"), ("/api/places", "places"),
    ("/api/suggest", "places"), ("/api/route", "itinerary"), ("/api/export", "export"), ("/api/auth", "auth"),
)


def feature_for_path(path: str) -> str:
    for prefix, name in _FEATURE_PREFIXES:
        if path.startswith(prefix):
            return name
    return "other"


_SECRET_LIKE = re.compile(r"(?i)(api[_-]?key|apikey|key|token|secret|authorization|bearer)\s*[=:]\s*[^\s&;,]+")
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-]{28,}")


def scrub(text: Any, limit: int = 220) -> str:
    """Error text that is safe to show an admin: no keys, no long tokens, one line, short."""
    out = " ".join(str(text or "").split())
    out = _SECRET_LIKE.sub(r"\1=[hidden]", out)
    out = _LONG_TOKEN.sub("[hidden]", out)
    return out[:limit]


def status_from_exception(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int) and 100 <= v < 600:
            return v
    m = re.search(r"\b(4\d\d|5\d\d)\b", str(exc))
    return int(m.group(1)) if m else None


def today() -> date:
    return datetime.now(timezone.utc).date()


class _Call:
    """Handed to `with usage_recorder.track(...) as u:` so the caller can add the HTTP status or token counts."""
    __slots__ = ("status", "tokens_in", "tokens_out")

    def __init__(self) -> None:
        self.status: Optional[int] = None
        self.tokens_in = 0
        self.tokens_out = 0


class UsageRecorder:
    def __init__(self) -> None:
        self._buffer: Dict[Tuple[date, str, str, str, str], list] = {}   # key -> [requests, total_ms, max_ms, tin, tout]
        self.failures: Deque[Dict[str, Any]] = deque(maxlen=100)          # recent failures (sanitised, memory only)
        self._latency: Dict[str, Deque[int]] = {}                         # provider -> recent response times
        self._recent_calls: Deque[float] = deque(maxlen=20000)            # timestamps, for the "last hour" burst check
        self._task: Optional[asyncio.Task] = None
        self._last_prune = 0.0

    # ------------------------------------------------------------ recording
    def record(self, provider: str, model: str, ok: bool, duration_ms: float, tokens_in: int = 0, tokens_out: int = 0,
               status: Optional[int] = None, error: Any = None, feature: Optional[str] = None) -> None:
        try:
            feat = feature or current_feature.get()
            ms = max(0, int(duration_ms))
            key = (today(), provider[:20], (model or "unknown")[:60], feat[:20], "ok" if ok else "error")
            row = self._buffer.get(key)
            if row is None:
                if len(self._buffer) >= MAX_BUFFER_KEYS:
                    return
                self._buffer[key] = [1, ms, ms, int(tokens_in or 0), int(tokens_out or 0)]
            else:
                row[0] += 1
                row[1] += ms
                row[2] = max(row[2], ms)
                row[3] += int(tokens_in or 0)
                row[4] += int(tokens_out or 0)
            self._latency.setdefault(provider, deque(maxlen=500)).append(ms)
            self._recent_calls.append(time.time())
            if not ok:
                self.failures.appendleft({
                    "time": datetime.now(timezone.utc).isoformat(), "provider": provider, "model": model, "feature": feat,
                    "status": status, "duration_ms": ms, "error": scrub(error),
                })
        except Exception:
            logger.debug("usage record skipped", exc_info=True)

    @contextlib.contextmanager
    def track(self, provider: str, model: str) -> Iterator[_Call]:
        """Times a call. It counts as a failure when it raises or when the HTTP status is 400 or higher
        (a 404 is a normal 'nothing found' answer, so it counts as a success)."""
        call = _Call()
        start = time.perf_counter()
        try:
            yield call
        except BaseException as exc:
            self.record(provider, model, False, (time.perf_counter() - start) * 1000, call.tokens_in, call.tokens_out,
                        call.status or status_from_exception(exc), exc)
            raise
        else:
            ms = (time.perf_counter() - start) * 1000
            bad = call.status is not None and call.status >= 400 and call.status != 404
            self.record(provider, model, not bad, ms, call.tokens_in, call.tokens_out, call.status,
                        f"HTTP {call.status}" if bad else None)

    # ------------------------------------------------------------ read helpers (memory only)
    def p95_ms(self, provider: str) -> Optional[int]:
        vals = sorted(self._latency.get(provider, ()))
        return vals[min(len(vals) - 1, int(len(vals) * 0.95))] if vals else None

    def calls_last_hour(self) -> int:
        cutoff = time.time() - 3600
        return sum(1 for t in self._recent_calls if t >= cutoff)

    # ------------------------------------------------------------ saving
    async def flush(self) -> None:
        if not self._buffer or not db_status()["ready"]:
            return
        pending, self._buffer = self._buffer, {}
        try:
            async with session_scope() as db:
                for (day, provider, model, feature, outcome), (n, total, mx, tin, tout) in pending.items():
                    pk = (day, provider, model, feature, outcome)
                    row = await db.get(ApiUsageDaily, pk)
                    if row is None:
                        db.add(ApiUsageDaily(day=day, provider=provider, model=model, feature=feature, outcome=outcome,
                                             requests=n, total_ms=total, max_ms=mx, tokens_in=tin, tokens_out=tout))
                    else:
                        row.requests = (row.requests or 0) + n
                        row.total_ms = (row.total_ms or 0) + total
                        row.max_ms = max(row.max_ms or 0, mx)
                        row.tokens_in = (row.tokens_in or 0) + tin
                        row.tokens_out = (row.tokens_out or 0) + tout
                await db.commit()
        except Exception as exc:
            logger.warning("Could not save API usage counters (will retry): %s", exc)
            for key, vals in pending.items():
                cur = self._buffer.get(key)
                if cur is None:
                    if len(self._buffer) < MAX_BUFFER_KEYS:
                        self._buffer[key] = vals
                else:
                    cur[0] += vals[0]; cur[1] += vals[1]; cur[2] = max(cur[2], vals[2]); cur[3] += vals[3]; cur[4] += vals[4]

    async def prune(self) -> None:
        try:
            async with session_scope() as db:
                await db.execute(delete(ApiUsageDaily).where(ApiUsageDaily.day < today() - timedelta(days=RETENTION_DAYS)))
                await db.commit()
        except Exception as exc:
            logger.info("API usage prune skipped: %s", exc)

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


usage_recorder = UsageRecorder()


def tokens_from_gemini(resp: Any) -> Tuple[int, int]:
    """(input tokens, output tokens incl. thinking) from a Gemini response; (0, 0) when not reported."""
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return 0, 0
    tin = getattr(um, "prompt_token_count", 0) or 0
    tout = (getattr(um, "candidates_token_count", 0) or 0) + (getattr(um, "thoughts_token_count", 0) or 0)
    try:
        return int(tin), int(tout)
    except Exception:
        return 0, 0
