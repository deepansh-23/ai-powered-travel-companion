"""Admin API routes.

All endpoints require `require_admin` dependency — unauthenticated → 401, non-admin → 403.
CSRF guard `require_same_origin` is applied to all state-changing methods.
Internal errors are sanitized before returning to the frontend.
"""

import math
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db_models import User
from app.security import require_same_origin
from admin.permissions import require_admin
from admin import service
from admin.schemas import (
    AdminItinerariesResponse,
    AdminItineraryDetail,
    AdminItineraryItem,
    AdminUserDetail,
    AdminUserItem,
    AdminUsersResponse,
    OverviewResponse,
    PatchUserRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

PAGE_SIZE = service.PAGE_SIZE


# ──────────────────────────── Overview ──────────────────────────────────────

@router.get("/overview", response_model=OverviewResponse)
async def overview(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await service.get_overview(db)
        return OverviewResponse(**data)
    except Exception as exc:
        logger.exception("Admin overview query failed")
        return OverviewResponse(
            total_users=0, total_admins=0, active_users=0, inactive_users=0,
            total_itineraries=0, registrations_last_7_days=0,
            database_healthy=False, db_error="Database query failed.",
        )


# ──────────────────────────── Users ─────────────────────────────────────────

@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    page: int = Query(1, ge=1),
    search: Optional[str] = Query(None, max_length=100),
    role: Optional[str] = Query(None),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        users, total = await service.list_users(db, page=page, search=search, role=role)
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
