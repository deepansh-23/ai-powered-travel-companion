"""Admin API routes.

All protected administrative endpoints require `require_admin` dependency.
- Unauthenticated -> 401
- Authenticated non-admin -> 403
- Admin without active step-up -> 401 (triggers re-auth modal)
- Active admin with step-up -> authorized

CSRF guard `require_same_origin` is applied to all state-changing methods.
Internal errors are sanitized before returning to the frontend.
"""

import asyncio
import logging
import math
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import db_status, get_db
from app.db_models import User
from app.security import require_same_origin
from app.services import auth_service
from app.services.activity_service import today as activity_today
from app.services.captcha_service import captcha_service
from admin import analytics, service, usage as usage_report
from admin.monitoring import metrics_tracker
from admin.permissions import (
    ADMIN_STEPUP_COOKIE,
    check_stepup_rate_limit,
    clear_stepup_failures,
    is_valid_admin_stepup,
    issue_admin_stepup_token,
    record_stepup_failure,
    require_admin,
    require_admin_basic,
    set_admin_stepup_cookie,
)
from admin.schemas import (
    AdminAuthStatusResponse,
    AdminFeedbackItem,
    AdminFeedbackResponse,
    AdminItinerariesResponse,
    AdminItineraryDetail,
    AdminItineraryItem,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminMonitoringResponse,
    AdminUserDetail,
    AdminUserItem,
    AdminUsersResponse,
    DeletionRequestItem,
    DeletionRequestsResponse,
    ResetPasswordResponse,
    DiagnosticsResponse,
    OverviewResponse,
    PatchFeedbackRequest,
    PatchUserRequest,
    SettingsResponse,
    StepupRequest,
    StepupResponse,
    SystemHealthResponse,
    UpdateSettingsRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

PAGE_SIZE = service.PAGE_SIZE


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_auth_cookie(request: Request, response: Response, raw_token: str) -> None:
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        settings.AUTH_COOKIE_NAME,
        raw_token,
        max_age=settings.AUTH_SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/",
    )


# ──────────────────────────── Auth Status & Step-Up ─────────────────────────

@router.get("/auth-status", response_model=AdminAuthStatusResponse)
async def admin_auth_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Check current authentication and admin step-up state quietly.

    Always returns 200 so the admin dashboard UI can display the right state
    (dashboard vs. step-up prompt vs. login redirect).
    """
    user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
    if user is None:
        return AdminAuthStatusResponse(
            authenticated=False,
            is_admin=False,
            stepup_valid=False,
            username=None,
        )

    is_adm = bool(getattr(user, "is_admin", False))
    stepup_cookie = request.cookies.get(ADMIN_STEPUP_COOKIE)
    stepup_ok = is_adm and is_valid_admin_stepup(stepup_cookie, user.id)

    return AdminAuthStatusResponse(
        authenticated=True,
        is_admin=is_adm,
        stepup_valid=stepup_ok,
        username=user.username,
    )


@router.post(
    "/stepup",
    response_model=StepupResponse,
    dependencies=[Depends(require_same_origin)],
)
async def admin_stepup(
    body: StepupRequest,
    request: Request,
    response: Response,
    admin: User = Depends(require_admin_basic),
):
    """Verify admin password to grant a short-lived step-up session (30 minutes, renewed while active).

    Rate-limited to prevent brute-forcing. Does not invalidate normal login on failure.
    """
    ip = _client_ip(request)
    rate_key = f"{admin.id}:{ip}"
    check_stepup_rate_limit(rate_key)

    if not body.password:
        record_stepup_failure(rate_key)
        raise HTTPException(status_code=400, detail="Password is required.")

    # Verify password with existing Argon2 hasher
    try:
        ok = auth_service._hasher.verify(admin.password_hash, body.password)
    except Exception:
        ok = False

    if not ok:
        record_stepup_failure(rate_key)
        raise HTTPException(status_code=401, detail="Invalid password.")

    # Success: clear failure counter and issue step-up cookie
    clear_stepup_failures(rate_key)
    token, expires = issue_admin_stepup_token(admin.id)
    set_admin_stepup_cookie(request, response, token)

    return StepupResponse(success=True, expires_at=expires)


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    dependencies=[Depends(require_same_origin)],
)
async def admin_login(
    body: AdminLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Dedicated CAPTCHA-protected admin login flow.

    - Verifies Google reCAPTCHA
    - Authenticates username and password securely
    - Checks admin role
    - Rejects unauthorized users with generic error (no account enumeration)
    - Grants full session and step-up token on success
    """
    ip = _client_ip(request)

    # 1. CAPTCHA verification
    if captcha_service.is_enabled():
        if not body.captcha_token:
            raise HTTPException(status_code=400, detail="Please complete the CAPTCHA security check.")
        captcha_result = await captcha_service.verify_token(body.captcha_token, ip)
        if not captcha_result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=captcha_result.get("message", "CAPTCHA verification failed."),
            )

    # 2. Authenticate credentials
    try:
        user = await auth_service.authenticate(db, body.username, body.password, ip)
    except auth_service.LockedOut as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except Exception:
        # Generic error message: identical for wrong password or non-existent user
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")

    # 3. Verify admin role
    if not getattr(user, "is_admin", False):
        # Do not disclose that the account exists or that password matched!
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")

    # 4. Create session and set cookies
    user_agent = request.headers.get("user-agent")
    raw_token = await auth_service.create_session(db, user, user_agent)
    _set_auth_cookie(request, response, raw_token)

    # Issue initial step-up token since password was just verified
    stepup_token, _ = issue_admin_stepup_token(user.id)
    set_admin_stepup_cookie(request, response, stepup_token)

    return AdminLoginResponse(
        success=True,
        redirect="/admin/",
        username=user.username,
    )


# ──────────────────────────── Overview ──────────────────────────────────────

@router.get("/overview", response_model=OverviewResponse)
async def overview(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await service.get_overview(db)
        return OverviewResponse(**data)
    except Exception:
        logger.exception("Admin overview query failed")
        return OverviewResponse(
            total_users=0, total_admins=0, active_users=0, inactive_users=0,
            total_itineraries=0, registrations_last_7_days=0,
            database_healthy=False, db_error="Database query failed.",
        )


# ──────────────────────────── API Monitoring ────────────────────────────────

@router.get("/monitoring", response_model=AdminMonitoringResponse)
async def get_api_monitoring(
    window: str = Query("15m", pattern="^(15m|24h)$"),
    _admin: User = Depends(require_admin),
):
    """Return real in-memory request metrics for the selected time window."""
    window_minutes = 15 if window == "15m" else 1440
    data = metrics_tracker.get_metrics(window_minutes=window_minutes)
    return AdminMonitoringResponse(**data)


# ──────────────────────────── System Health ─────────────────────────────────

@router.get("/system-health", response_model=SystemHealthResponse)
async def get_system_health(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Detailed system diagnostic health check for administrators.

    Measures PostgreSQL query latency with a safe timeout and pulls real
    application uptime and API monitoring error rates.
    """
    now = datetime.now(timezone.utc).isoformat()
    uptime_seconds = int(time.time() - metrics_tracker.start_time)

    # Human-readable uptime
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    secs = uptime_seconds % 60
    uptime_parts = []
    if days > 0:
        uptime_parts.append(f"{days}d")
    if hours > 0 or days > 0:
        uptime_parts.append(f"{hours}h")
    uptime_parts.append(f"{minutes}m {secs}s")
    uptime_human = " ".join(uptime_parts)

    # Check PostgreSQL connection and latency
    db_connected = False
    db_latency_ms = None
    db_status_text = "Disconnected"

    try:
        t0 = time.perf_counter()
        # Strictly timed query (2.0s timeout) to avoid hangs
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        db_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        db_connected = True
        db_status_text = "Connected"
    except asyncio.TimeoutError:
        db_status_text = "Timeout (>2000ms)"
        logger.warning("System health DB check timed out")
    except Exception as exc:
        db_status_text = "Error"
        logger.warning(f"System health DB check failed: {exc}")

    # Check current monitoring metrics for error rate
    metrics = metrics_tracker.get_metrics(window_minutes=15)
    error_rate = metrics["error_rate_percent"]
    total_reqs = metrics["total_requests"]

    # Compute overall status
    if not db_connected:
        overall_status = "Unavailable"
    elif (db_latency_ms and db_latency_ms > 500) or error_rate >= 5.0:
        overall_status = "Degraded"
    else:
        overall_status = "Healthy"

    # Dependency status (boolean configured indicators only — no keys exposed)
    dependencies = {
        "FastAPI Core": {
            "status": "Healthy",
            "info": f"Running v{settings.APP_VERSION}",
        },
        "Aiven PostgreSQL": {
            "status": "Healthy" if db_connected else "Unavailable",
            "info": f"{db_latency_ms}ms query latency" if db_connected else db_status_text,
        },
        "Geoapify Places API": {
            "status": "Configured" if bool(settings.GEOAPIFY_API_KEY) else "Not configured",
            "info": "Active for live places & routing" if bool(settings.GEOAPIFY_API_KEY) else "Using local mock dataset",
        },
        "Gemini AI": {
            "status": "Configured" if bool(settings.GEMINI_API_KEY) else "Not configured",
            "info": f"Model: {settings.AI_MODEL}" if bool(settings.GEMINI_API_KEY) else "Using local mock responses",
        },
        "Google reCAPTCHA": {
            "status": "Configured" if captcha_service.is_enabled() else "Dev Mode",
            "info": "Verification active" if captcha_service.is_enabled() else "Local bypass active",
        },
    }

    return SystemHealthResponse(
        status=overall_status,
        timestamp=now,
        app_status="Running",
        uptime_seconds=uptime_seconds,
        uptime_human=uptime_human,
        python_version=sys.version.split()[0],
        app_version=settings.APP_VERSION,
        database_status=db_status_text,
        database_connected=db_connected,
        database_latency_ms=db_latency_ms,
        last_successful_check=now if db_connected else "Unavailable",
        api_error_rate_percent=error_rate,
        api_total_requests=total_reqs,
        dependencies=dependencies,
    )


# ──────────────────────────── Users ─────────────────────────────────────────

@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None, max_length=100),
    role: Optional[str] = Query(None),
    account_status: Optional[str] = Query(None, alias="status", pattern="^(active|suspended|deletion_requested)$"),
    sort: Optional[str] = Query(None, pattern="^(newest|oldest|last_active|username)$"),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        users, total = await service.list_users(db, page=page, search=search, role=role, status=account_status, sort=sort)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        return AdminUsersResponse(
            users=[AdminUserItem(**u) for u in users],
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            pages=pages,
        )
    except Exception:
        logger.exception("Admin list_users failed")
        raise HTTPException(status_code=500, detail="Failed to fetch users.")


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await service.get_user(db, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return AdminUserDetail(**data)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserDetail,
    dependencies=[Depends(require_same_origin)],
)
async def patch_user(
    user_id: str,
    body: PatchUserRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await service.patch_user(
            db,
            target_id=user_id,
            acting_admin_id=admin.id,
            is_active=body.is_active,
            is_admin=body.is_admin,
        )
        return AdminUserDetail(**data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin patch_user failed")
        raise HTTPException(status_code=500, detail="Failed to update user.")


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_user(db, target_id=user_id, acting_admin_id=admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin delete_user failed")
        raise HTTPException(status_code=500, detail="Failed to delete user.")


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ResetPasswordResponse,
    dependencies=[Depends(require_same_origin)],
)
async def reset_user_password(
    user_id: str,
    response: Response,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Gives the user a new random password (shown ONCE to the admin) and signs them out everywhere."""
    response.headers["Cache-Control"] = "no-store"
    try:
        temp = await service.reset_user_password(db, user_id, admin.id)
        return ResetPasswordResponse(
            temporary_password=temp,
            message="Share this password with the user privately. They are signed out everywhere and should change it after logging in.",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin reset_user_password failed")
        raise HTTPException(status_code=500, detail="Failed to reset the password.")


@router.get("/deletion-requests", response_model=DeletionRequestsResponse)
async def list_deletion_requests(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    items = await service.list_deletion_requests(db)
    return DeletionRequestsResponse(requests=[DeletionRequestItem(**i) for i in items], total=len(items))


@router.post("/deletion-requests/{request_id}/approve", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_same_origin)])
async def approve_deletion_request(
    request_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.approve_deletion_request(db, request_id, admin.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin approve_deletion_request failed")
        raise HTTPException(status_code=500, detail="Failed to delete the account.")


@router.post("/deletion-requests/{request_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_same_origin)])
async def dismiss_deletion_request(
    request_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.dismiss_deletion_request(db, request_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ──────────────────────────── AI & API usage monitor ─────────────────────────

@router.get("/usage")
async def get_usage(
    start: Optional[str] = Query(None, max_length=10),
    end: Optional[str] = Query(None, max_length=10),
    days: int = Query(30, ge=1, le=366),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """AI requests by model and feature, failures, response times, external API usage, estimated spend and alerts."""
    try:
        s, e = analytics.parse_range(start, end, days, activity_today())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return await usage_report.build_usage(db, s, e)
    except Exception:
        logger.exception("Admin usage report failed")
        raise HTTPException(status_code=500, detail="Failed to build the usage report.")


@router.get("/usage/settings")
async def get_usage_settings(_admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    limits = await usage_report.get_limits(db)
    prices = await usage_report.get_prices(db)
    return {"limits": limits, "prices": {k: list(v) for k, v in prices.items()},
            "default_prices": {k: list(v) for k, v in usage_report.DEFAULT_PRICES.items()}}


@router.put("/usage/settings", dependencies=[Depends(require_same_origin)])
async def put_usage_settings(
    body: Dict[str, Any] = Body(...),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Saves alert limits and/or model prices. Only these two keys are accepted; nothing else can be stored here."""
    extra = set(body) - {"limits", "prices"}
    if extra:
        raise HTTPException(status_code=400, detail="Unknown field: " + ", ".join(sorted(map(str, extra))))
    if body.get("limits") is not None and not isinstance(body["limits"], dict):
        raise HTTPException(status_code=400, detail="limits must be an object.")
    if body.get("prices") is not None and not isinstance(body["prices"], dict):
        raise HTTPException(status_code=400, detail="prices must be an object.")
    try:
        await usage_report.save_limits_and_prices(db, body.get("limits"), body.get("prices"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await get_usage_settings(_admin, db)


@router.post("/usage/serpapi-quota", dependencies=[Depends(require_same_origin)])
async def check_serpapi_quota(_admin: User = Depends(require_admin)):
    """Asks SerpApi how many searches are left (its free account endpoint; costs no search)."""
    return await usage_report.serpapi_account(force=True)


# ──────────────────────────── Analytics ─────────────────────────────────────

@router.get("/analytics")
async def get_analytics(
    start: Optional[str] = Query(None, max_length=10),
    end: Optional[str] = Query(None, max_length=10),
    days: int = Query(30, ge=1, le=366),
    interval: str = Query("day", pattern="^(day|week|month)$"),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Active users, registrations, feature usage and trends for a date range (UTC days)."""
    try:
        s, e = analytics.parse_range(start, end, days, activity_today())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        return await analytics.build_analytics(db, s, e, interval)
    except Exception:
        logger.exception("Admin analytics failed")
        raise HTTPException(status_code=500, detail="Failed to build analytics.")


# ──────────────────────────── Itineraries ───────────────────────────────────

@router.get("/itineraries", response_model=AdminItinerariesResponse)
async def list_itineraries(
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None, max_length=200),
    feature_type: Optional[str] = Query(None),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await service.list_itineraries(db, page=page, search=search, feature_type=feature_type)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        return AdminItinerariesResponse(
            itineraries=[AdminItineraryItem(**i) for i in items],
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            pages=pages,
        )
    except Exception:
        logger.exception("Admin list_itineraries failed")
        raise HTTPException(status_code=500, detail="Failed to fetch itineraries.")


@router.get("/itineraries/{itinerary_id}", response_model=AdminItineraryDetail)
async def get_itinerary(
    itinerary_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await service.get_itinerary(db, itinerary_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Itinerary not found.")
    return AdminItineraryDetail(**data)


@router.delete(
    "/itineraries/{itinerary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_same_origin)],
)
async def delete_itinerary(
    itinerary_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_itinerary(db, itinerary_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Admin delete_itinerary failed")
        raise HTTPException(status_code=500, detail="Failed to delete itinerary.")


# ──────────────────────────── Settings ──────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await service.get_settings(db)
        return SettingsResponse(**data)
    except Exception:
        logger.exception("Admin get_settings failed")
        raise HTTPException(status_code=500, detail="Failed to load settings.")


@router.put("/settings", response_model=SettingsResponse, dependencies=[Depends(require_same_origin)])
async def update_settings(
    body: UpdateSettingsRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    changes = body.model_dump(exclude_unset=True)
    confirmed = bool(changes.pop("confirm_disruptive", False))
    try:
        current = await service.get_settings(db)
        risky = service.disruptive_changes(current, changes)
        if risky and not confirmed:
            raise HTTPException(
                status_code=400,
                detail="Confirmation required for: " + ", ".join(risky) + ".",
            )
        data = await service.update_settings(db, changes)
        return SettingsResponse(**data)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin update_settings failed")
        raise HTTPException(status_code=500, detail="Failed to save settings.")


# ──────────────────────────── Feedback Management ───────────────────────────

@router.get("/feedback", response_model=AdminFeedbackResponse)
async def list_feedback(
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None, max_length=100),
    service_used: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    rating: Optional[int] = Query(None, ge=1, le=5),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total, summary = await service.list_admin_feedback(
            db, page=page, page_size=PAGE_SIZE, search=search,
            service_used=service_used, status=status, rating=rating,
        )
        pages = max(1, math.ceil(total / PAGE_SIZE))
        return AdminFeedbackResponse(
            items=[AdminFeedbackItem(**i) for i in items],
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            pages=pages,
            summary=summary,
        )
    except Exception:
        logger.exception("Admin list_feedback failed")
        raise HTTPException(status_code=500, detail="Failed to fetch feedback.")


@router.get("/feedback/{feedback_id}", response_model=AdminFeedbackItem)
async def get_feedback(
    feedback_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await service.get_admin_feedback(db, feedback_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Feedback not found.")
    return AdminFeedbackItem(**data)


@router.patch("/feedback/{feedback_id}", response_model=AdminFeedbackItem, dependencies=[Depends(require_same_origin)])
async def patch_feedback(
    feedback_id: str,
    body: PatchFeedbackRequest,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await service.patch_admin_feedback(
            db, feedback_id=feedback_id, status=body.status, admin_notes=body.admin_notes,
        )
        return AdminFeedbackItem(**data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Admin patch_feedback failed")
        raise HTTPException(status_code=500, detail="Failed to update feedback.")


@router.delete("/feedback/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_same_origin)])
async def delete_feedback(
    feedback_id: str,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await service.delete_admin_feedback(db, feedback_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("Admin delete_feedback failed")
        raise HTTPException(status_code=500, detail="Failed to delete feedback.")


# ──────────────────────────── Diagnostics ───────────────────────────────────

@router.get("/diagnostics", response_model=DiagnosticsResponse)
async def get_diagnostics(
    level: str = Query("all", pattern="^(all|4xx|5xx)$"),
    search: Optional[str] = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=100),
    _admin: User = Depends(require_admin),
):
    try:
        data = metrics_tracker.get_diagnostics(level=level, search=search, limit=limit)
        data["database_status"] = "Connected" if db_status()["ready"] else "Unavailable"
        return DiagnosticsResponse(**data)
    except Exception:
        logger.exception("Admin get_diagnostics failed")
        raise HTTPException(status_code=500, detail="Failed to fetch diagnostics.")

