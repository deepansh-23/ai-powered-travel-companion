"""Admin authorization and step-up authentication dependency.

All admin endpoints depend on `require_admin`.
- Authenticated admin with active step-up -> returns User
- Authenticated admin without active step-up -> 401 with step-up required flag
- Authenticated non-admin -> 403
- Unauthenticated -> 401

Authorization is fully server-side — no frontend role or timestamp is trusted.
"""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.db_models import User
from app.security import derive_fallback_secret
from app.services import auth_service

ADMIN_STEPUP_COOKIE = "slg_admin_stepup"
STEPUP_LIFETIME_SECONDS = 30 * 60   # idle timeout: renewed while the admin keeps using the dashboard
STEPUP_RENEW_BELOW_SECONDS = 20 * 60  # re-issue the cookie once less than this is left

_FALLBACK_ADMIN_SECRET = derive_fallback_secret("admin-stepup")


def _stepup_secret() -> bytes:
    return (settings.AUTH_SECRET or _FALLBACK_ADMIN_SECRET).encode()


def issue_admin_stepup_token(user_id: str) -> Tuple[str, int]:
    """Issue a signed step-up token valid for STEPUP_LIFETIME_SECONDS."""
    expires = int(time.time()) + STEPUP_LIFETIME_SECONDS
    nonce = secrets.token_hex(8)
    payload = f"{user_id}.{expires}.{nonce}"
    sig = hmac.new(_stepup_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}", expires


def is_valid_admin_stepup(token: Optional[str], user_id: str) -> bool:
    """Validate step-up signature, expiry, and user binding."""
    if not token or token.count(".") != 3:
        return False
    tok_user_id, expires_str, nonce, sig = token.split(".")
    if tok_user_id != user_id:
        return False
    try:
        expires = int(expires_str)
    except ValueError:
        return False
    if expires <= time.time():
        return False
    expected = hmac.new(_stepup_secret(), f"{tok_user_id}.{expires_str}.{nonce}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def stepup_seconds_left(token: Optional[str]) -> int:
    try:
        return max(0, int(token.split(".")[1]) - int(time.time()))  # token = user.expires.nonce.sig
    except Exception:
        return 0


def set_admin_stepup_cookie(request: Request, response: Response, token: str) -> None:
    """Set secure short-lived step-up cookie."""
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        ADMIN_STEPUP_COOKIE,
        token,
        max_age=STEPUP_LIFETIME_SECONDS,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
    )


def clear_admin_stepup_cookie(response: Response) -> None:
    """Clear step-up cookie on logout or invalidation."""
    response.delete_cookie(ADMIN_STEPUP_COOKIE, path="/")


# ── Failed step-up rate limiter ─────────────────────────────────────────────
_stepup_failures: Dict[str, List[float]] = defaultdict(list)


def check_stepup_rate_limit(key: str) -> None:
    """Allow at most 5 failed step-up attempts per 15 minutes per IP/user."""
    now = time.time()
    recent = [t for t in _stepup_failures[key] if now - t < 900]
    _stepup_failures[key] = recent
    if len(recent) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed verification attempts. Please wait 15 minutes before trying again.",
        )


def record_stepup_failure(key: str) -> None:
    _stepup_failures[key].append(time.time())


def clear_stepup_failures(key: str) -> None:
    _stepup_failures.pop(key, None)


# ── Dependencies ────────────────────────────────────────────────────────────

async def require_admin_basic(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Allow authenticated admin users (without enforcing step-up).

    Used for step-up verification and auth status check.
    """
    user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user


async def require_admin(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> User:
    """FastAPI dependency: allow only authenticated admin users with active step-up.

    - Unauthenticated -> 401
    - Authenticated non-admin -> 403
    - Authenticated admin, but step-up missing or expired -> 401 with reauth header
    - Active admin with valid step-up -> returns User
    """
    user = await require_admin_basic(request, db)

    stepup_token = request.cookies.get(ADMIN_STEPUP_COOKIE)
    if not is_valid_admin_stepup(stepup_token, user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up re-authentication required.",
            headers={"X-Admin-Reauth-Required": "true"},
        )

    # Sliding idle timeout: an admin who keeps working is not asked for the password again.
    if stepup_seconds_left(stepup_token) < STEPUP_RENEW_BELOW_SECONDS:
        fresh, _ = issue_admin_stepup_token(user.id)
        set_admin_stepup_cookie(request, response, fresh)

    return user
