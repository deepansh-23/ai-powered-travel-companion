"""Account routes: register, login, logout, me, recover, change password."""

import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import db_status, get_db
from app.db_models import AccountDeletionRequest, User
from app.models.auth import (
    AuthResponse, ChangePasswordRequest, DeleteAccountRequest, DeletionRequestBody, GuestStartRequest, LoginRequest, MeResponse,
    RecoverRequest, RegisterRequest, UserPublic,
)
from app.security import (
    get_current_user_optional, is_valid_guest_token, issue_guest_token, require_same_origin, require_user,
)
from app.services import auth_service
from app.services.captcha_service import captcha_service
from app.services.site_settings_guard import require_setting

router = APIRouter(prefix="/api/auth", tags=["Auth"], dependencies=[Depends(require_same_origin)])


_guest_starts: Dict[str, List[float]] = defaultdict(list)


def _guest_rate_limited(ip: str) -> bool:
    """At most GUEST_MAX_STARTS_PER_HOUR_PER_IP new guest sessions per IP per hour."""
    now = time.time()
    recent = [t for t in _guest_starts[ip] if now - t < 3600]
    if len(recent) >= settings.GUEST_MAX_STARTS_PER_HOUR_PER_IP:
        _guest_starts[ip] = recent
        return True
    recent.append(now)
    _guest_starts[ip] = recent
    return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        is_admin=bool(getattr(user, "is_admin", False)),
        created_at=user.created_at,
    )


def _set_cookie(request: Request, response: Response, raw_token: str) -> None:
    response.set_cookie(
        settings.AUTH_COOKIE_NAME,
        raw_token,
        max_age=settings.AUTH_SESSION_DAYS * 86400,
        httponly=True,                      # JavaScript cannot read it
        samesite="lax",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        path="/",
    )


async def _check_captcha(token: Optional[str], ip: str) -> None:
    """Human check on register / login / recover (only when CAPTCHA keys are configured)."""
    if not captcha_service.is_enabled():
        return
    if not token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please tick the CAPTCHA box first.")
    result = await captcha_service.verify_token(token, ip)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("message", "CAPTCHA verification failed."))


def _fail(exc: auth_service.AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/me", response_model=MeResponse)
async def me(request: Request):
    """Who is logged in (or is this a guest)? Always 200, so pages can check quietly."""
    guest = is_valid_guest_token(request.cookies.get(settings.GUEST_COOKIE_NAME))
    info = db_status()
    if not info["ready"]:
        return MeResponse(authenticated=False, accounts_available=False, guest=guest)
    from app.db import get_db as _gd  # open a short-lived session without raising 503
    async for db in _gd():
        user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
        return MeResponse(
            authenticated=user is not None,
            user=_public(user) if user else None,
            guest=guest and user is None,
        )
    return MeResponse(authenticated=False, guest=guest)


@router.post("/guest")
async def start_guest(req: GuestStartRequest, request: Request, response: Response):
    """Start a guest session: planning tools work, nothing is saved to an account."""
    await require_setting("guest_mode_enabled", "Guest mode is temporarily disabled. Please log in.")
    ip = _client_ip(request)
    if _guest_rate_limited(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many guest sessions from this network. Please try again later.")
    await _check_captcha(req.captcha_token, ip)
    response.set_cookie(
        settings.GUEST_COOKIE_NAME,
        issue_guest_token(),
        max_age=settings.GUEST_SESSION_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        path="/",
    )
    return {"status": "guest_started", "guest": True}


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await require_setting("allow_registration", "New account registration is temporarily disabled.")
    ip = _client_ip(request)
    await _check_captcha(req.captcha_token, ip)
    try:
        user, recovery = await auth_service.register(db, req.username, req.password)
    except auth_service.AuthError as exc:
        raise _fail(exc)
    raw = await auth_service.create_session(db, user, request.headers.get("user-agent"))
    _set_cookie(request, response, raw)
    return AuthResponse(user=_public(user), recovery_code=recovery)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    await _check_captcha(req.captcha_token, ip)
    try:
        user = await auth_service.authenticate(db, req.username, req.password, ip)
    except auth_service.AuthError as exc:
        raise _fail(exc)
    raw = await auth_service.create_session(db, user, request.headers.get("user-agent"))
    _set_cookie(request, response, raw)
    return AuthResponse(user=_public(user))


@router.post("/logout")
async def logout(request: Request, response: Response):
    """Ends a login session and/or a guest session. Works even if the database is down."""
    raw = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if raw:
        from app.db import get_db as _gd
        try:
            async for db in _gd():
                await auth_service.end_session(db, raw)
        except HTTPException:
            pass  # accounts DB unavailable: cookies are still cleared below
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(settings.GUEST_COOKIE_NAME, path="/")
    response.delete_cookie("slg_admin_stepup", path="/")
    return {"status": "logged_out"}


@router.post("/recover", response_model=AuthResponse)
async def recover(req: RecoverRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Forgot password: reset with the one-time recovery code shown at sign-up."""
    ip = _client_ip(request)
    await _check_captcha(req.captcha_token, ip)
    try:
        user, new_code = await auth_service.recover_account(db, req.username, req.recovery_code, req.new_password, ip)
    except auth_service.AuthError as exc:
        raise _fail(exc)
    raw = await auth_service.create_session(db, user, request.headers.get("user-agent"))
    _set_cookie(request, response, raw)
    return AuthResponse(user=_public(user), recovery_code=new_code)


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.change_password(db, user, req.current_password, req.new_password)
    except auth_service.AuthError as exc:
        raise _fail(exc)
    return {"status": "password_changed"}


@router.post("/delete-account")
async def delete_account(req: DeleteAccountRequest, response: Response, user: User = Depends(require_user),
                         db: AsyncSession = Depends(get_db)):
    """Permanently delete the logged-in account (password required)."""
    try:
        await auth_service.delete_account(db, user, req.password)
    except auth_service.AuthError as exc:
        raise _fail(exc)
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(settings.GUEST_COOKIE_NAME, path="/")
    return {"status": "account_deleted"}


# ---------------------------------------------------------------- ask an admin to delete the account
@router.get("/delete-request")
async def get_delete_request(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    row = (await db.execute(select(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))).scalar_one_or_none()
    return {"pending": bool(row and row.status == "pending"), "requested_at": row.requested_at if row else None}


@router.post("/delete-request", dependencies=[Depends(require_same_origin)])
async def request_account_deletion(req: DeletionRequestBody, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Asks an administrator to delete this account. Nothing is deleted until an admin approves it."""
    from sqlalchemy import select
    reason = " ".join((req.reason or "").split())[:300]
    row = (await db.execute(select(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))).scalar_one_or_none()
    if row is None:
        db.add(AccountDeletionRequest(user_id=user.id, reason=reason or None, status="pending"))
    else:
        row.reason, row.status = (reason or row.reason), "pending"
    await db.commit()
    return {"status": "requested"}


@router.delete("/delete-request", dependencies=[Depends(require_same_origin)])
async def withdraw_deletion_request(user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))
    await db.commit()
    return {"status": "withdrawn"}
