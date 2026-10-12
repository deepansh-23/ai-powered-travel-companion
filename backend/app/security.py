"""Shared request guards."""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.db_models import User
from app.services import auth_service
from app.services.captcha_service import captcha_service

CAPTCHA_COOKIE = "slg_human"


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


async def require_same_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated writes: a browser's Origin header must be this site."""
    origin = request.headers.get("origin")
    if not origin:
        return  # not a cross-site browser request
    host = request.headers.get("host", "")
    allowed = {f"http://{host}", f"https://{host}", *settings.CORS_ORIGINS}
    if origin not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Request blocked (unexpected origin).")
