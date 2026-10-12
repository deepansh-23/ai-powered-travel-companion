"""Account routes: register, login, logout, me, recover, change password."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import db_status, get_db
from app.db_models import User
from app.models.auth import (
    AuthResponse, ChangePasswordRequest, LoginRequest, MeResponse, RecoverRequest, RegisterRequest, UserPublic,
)
from app.security import get_current_user_optional, require_same_origin, require_user
from app.services import auth_service
from app.services.captcha_service import captcha_service

router = APIRouter(prefix="/api/auth", tags=["Auth"], dependencies=[Depends(require_same_origin)])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _public(user: User) -> UserPublic:
    return UserPublic(id=user.id, username=user.username, created_at=user.created_at)


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
    """Who is logged in? Always 200, so pages can check quietly."""
    info = db_status()
    if not info["ready"]:
        return MeResponse(authenticated=False, accounts_available=False)
    from app.db import get_db as _gd  # open a short-lived session without raising 503
    async for db in _gd():
        user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
        return MeResponse(authenticated=user is not None, user=_public(user) if user else None)
    return MeResponse(authenticated=False)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
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
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await auth_service.end_session(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
    response.delete_cookie(settings.AUTH_COOKIE_NAME, path="/")
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
