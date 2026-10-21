"""Admin Pydantic schemas (request/response models)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# ──────────────────────────── Overview ──────────────────────────────────────

class OverviewResponse(BaseModel):
    total_users: int
    total_admins: int
    active_users: int
    inactive_users: int
    total_itineraries: int
    registrations_last_7_days: int
    database_healthy: bool
    db_error: Optional[str] = None


# ──────────────────────────── Users ─────────────────────────────────────────

class AdminUserItem(BaseModel):
    id: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    itinerary_count: int = 0


class AdminUsersResponse(BaseModel):
    users: List[AdminUserItem]
    total: int
    page: int
    page_size: int
    pages: int


class AdminUserDetail(AdminUserItem):
    pass


class PatchUserRequest(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


# ──────────────────────────── Itineraries ───────────────────────────────────

class AdminItineraryItem(BaseModel):
    id: str
    user_id: str
    username: Optional[str] = None
    feature_type: str
    title: str
    preview: str
    created_at: Optional[datetime] = None


class AdminItinerariesResponse(BaseModel):
    itineraries: List[AdminItineraryItem]
    total: int
    page: int
    page_size: int
    pages: int


class AdminItineraryDetail(AdminItineraryItem):
    payload: dict = {}
