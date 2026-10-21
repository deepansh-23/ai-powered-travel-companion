"""Enforces admin-controlled site settings on the public API.

- Maintenance mode: non-admin /api requests get a 503 (admins, auth and health stay available).
- Registration / guest mode / new reviews: small helper checks used by the routes.

Everything fails OPEN: if the database or settings cannot be read, the site keeps working.
"""

import logging

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.db import db_status, get_db

logger = logging.getLogger(__name__)

# Always reachable during maintenance so admins can sign in and the site can show the notice.
MAINTENANCE_ALLOWED_PREFIXES = (
    "/api/admin",
    "/api/auth",
    "/api/settings",
    "/api/health",
    "/api/captcha",
)


async def load_settings() -> dict:
    """Cached settings (5 s). Returns {} when the database is unavailable."""
    if not db_status()["ready"]:
        return {}
    from admin import service
    cached = service.peek_cached_settings()
    if cached is not None:
        return cached
    try:
        async for db in get_db():
            return await service.get_cached_settings(db)
    except Exception:
        logger.warning("Could not load site settings; using defaults.")
    return {}


async def _is_admin_request(request: Request) -> bool:
    from admin import service  # noqa: F401  (keeps import order explicit)
    from app.services import auth_service
    raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if not raw:
        return False
    try:
        async for db in get_db():
            user = await auth_service.get_user_for_token(db, raw)
            return bool(user and getattr(user, "is_admin", False))
    except Exception:
        return False
    return False


class MaintenanceModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api") or path.startswith(MAINTENANCE_ALLOWED_PREFIXES):
            return await call_next(request)
        try:
            current = await load_settings()
            if current.get("maintenance_mode") and not await _is_admin_request(request):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "The site is under maintenance. Please try again shortly."},
                    headers={"Retry-After": "300"},
                )
        except Exception:
            logger.exception("Maintenance check failed; allowing request.")
        return await call_next(request)


async def require_setting(key: str, message: str) -> None:
    """Raise 403 when the boolean setting `key` is switched off (defaults to allowed)."""
    current = await load_settings()
    if current.get(key, True) is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)
