"""Shared request guards."""

import hashlib
import hmac
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.db_models import User
from app.services import auth_service
from app.services.captcha_service import captcha_service

CAPTCHA_COOKIE = "slg_human"

# ---------------------------------------------------------------- guest sessions
# A guest session is a signed, expiring cookie. It proves "this browser chose guest mode"
# so the planner and search tools work, but it is never linked to a user profile.
_FALLBACK_GUEST_SECRET = secrets.token_hex(32)


def _guest_secret() -> bytes:
    return (settings.AUTH_SECRET or _FALLBACK_GUEST_SECRET).encode()


def issue_guest_token() -> str:
    expires = int(time.time()) + int(settings.GUEST_SESSION_HOURS) * 3600
    payload = f"{expires}.{secrets.token_urlsafe(8)}"
    sig = hmac.new(_guest_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def is_valid_guest_token(token: Optional[str]) -> bool:
    if not token or token.count(".") != 2:
        return False
    expires_str, nonce, sig = token.split(".")
    try:
        expires = int(expires_str)
    except ValueError:
        return False
    expected = hmac.new(_guest_secret(), f"{expires_str}.{nonce}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected) and expires > time.time()


async def require_human(request: Request) -> None:
    """Blocks costly/abusable endpoints until the session passed the CAPTCHA.

    No-op when CAPTCHA is not configured (local development).
    """
    if not captcha_service.is_enabled():
        return
    if not captcha_service.is_valid_session_token(request.cookies.get(CAPTCHA_COOKIE)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Human verification required. Please complete the security check.",
        )


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    """The logged-in user from the session cookie, or None."""
    return await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))


async def require_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Blocks a route unless the browser has a valid login session."""
    user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to use this feature.",
        )
    return user


async def require_user_or_guest(request: Request) -> Optional[User]:
    """Lets a logged-in user OR a guest through (returns the User, or None for a guest).

    Used for the planning tools (itinerary, transport, hotels, area guide). Anything that
    stores personal data (history, saved sessions, reviews, account) still uses require_user.
    A guest keeps working even if the accounts database is temporarily down.
    """
    raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if raw:
        agen = get_db()
        try:
            db = await agen.__anext__()
            user = await auth_service.get_user_for_token(db, raw)
            if user is not None:
                return user
        except (HTTPException, StopAsyncIteration):
            pass  # database unavailable: fall through to the guest check
        finally:
            await agen.aclose()
    if is_valid_guest_token(request.cookies.get(settings.GUEST_COOKIE_NAME)):
        return None
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please log in or continue as a guest to use this feature.",
    )


async def require_same_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated writes: a browser's Origin header must be this site."""
    origin = request.headers.get("origin")
    if not origin:
        return  # not a cross-site browser request
    host = request.headers.get("host", "")
    allowed = {f"http://{host}", f"https://{host}", *settings.CORS_ORIGINS}
    if origin not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request blocked (unexpected origin).")
