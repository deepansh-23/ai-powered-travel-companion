"""Admin Pydantic schemas (request/response models)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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


# ──────────────────────────── Auth / Step-Up / Login ────────────────────────

class AdminLoginRequest(BaseModel):
    username: str = Field("", max_length=100)
    password: str = Field("", max_length=300)
    captcha_token: Optional[str] = None


class AdminLoginResponse(BaseModel):
    success: bool
    redirect: str = "/admin/"
    username: str


class StepupRequest(BaseModel):
    password: str = Field("", max_length=300)


class StepupResponse(BaseModel):
    success: bool
    expires_at: int
    message: str = "Admin authorization granted for 30 minutes of activity."


class AdminAuthStatusResponse(BaseModel):
    authenticated: bool
    is_admin: bool
    stepup_valid: bool
    username: Optional[str] = None


# ──────────────────────────── API Monitoring ────────────────────────────────

class SlowestEndpointItem(BaseModel):
    endpoint: str
    avg_duration_ms: float
    max_duration_ms: float
    count: int


class ErrorEndpointItem(BaseModel):
    endpoint: str
    error_count: int
    last_status_code: int


class RecentFailureItem(BaseModel):
    timestamp: str
    method: str
    path: str
    status_code: int
    duration_ms: float


class AdminMonitoringResponse(BaseModel):
    window_minutes: int
    window_label: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    c4xx_count: int
    c5xx_count: int
    error_rate_percent: float
    avg_response_time_ms: float
    slowest_endpoints: List[SlowestEndpointItem]
    endpoints_with_most_errors: List[ErrorEndpointItem]
    recent_failures: List[RecentFailureItem]
    process_started_at: str
    uptime_seconds: int
    total_lifetime_requests: int
    is_in_memory: bool = True


# ──────────────────────────── System Health ─────────────────────────────────

class SystemHealthResponse(BaseModel):
    status: str  # "Healthy" | "Degraded" | "Unavailable"
    timestamp: str
    app_status: str
    uptime_seconds: int
    uptime_human: str
    python_version: str
    app_version: str
    database_status: str
    database_connected: bool
    database_latency_ms: Optional[float] = None
    last_successful_check: str
    api_error_rate_percent: float
    api_total_requests: int
    dependencies: Dict[str, Any]


# ──────────────────────────── Settings ──────────────────────────────────────

class SettingsResponse(BaseModel):
    maintenance_mode: bool
    public_notice_enabled: bool
    public_notice_text: str
    guest_mode_enabled: bool
    allow_registration: bool
    allow_reviews: bool = True
    updated_at: Optional[datetime] = None


class UpdateSettingsRequest(BaseModel):
    maintenance_mode: Optional[bool] = None
    public_notice_enabled: Optional[bool] = None
    public_notice_text: Optional[str] = Field(None, max_length=300)
    guest_mode_enabled: Optional[bool] = None
    allow_registration: Optional[bool] = None
    allow_reviews: Optional[bool] = None
    # Must be true when the change would shut something off for visitors (see service.DISRUPTIVE_VALUES)
    confirm_disruptive: bool = False


class PublicSettingsResponse(BaseModel):
    maintenance_mode: bool
    public_notice_enabled: bool
    public_notice_text: str
    guest_mode_enabled: bool
    allow_registration: bool
    allow_reviews: bool = True


# ──────────────────────────── Feedback Management ───────────────────────────

class AdminFeedbackItem(BaseModel):
    id: str
    username: Optional[str] = None
    rating: int
    comment: str
    service_used: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: Optional[datetime] = None


class AdminFeedbackSummary(BaseModel):
    total: int
    pending: int
    reviewed: int
    resolved: int
    avg_rating: float


class AdminFeedbackResponse(BaseModel):
    items: List[AdminFeedbackItem]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AdminFeedbackSummary


class PatchFeedbackRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(pending|reviewed|resolved)$")
    admin_notes: Optional[str] = Field(None, max_length=1000)


# ──────────────────────────── Diagnostics ───────────────────────────────────

class DiagnosticEvent(BaseModel):
    id: str
    timestamp: str
    method: str
    endpoint: str
    status_code: int
    error_summary: str
    duration_ms: float
    client_ip_masked: str


class DiagnosticsResponse(BaseModel):
    items: List[DiagnosticEvent]
    total_recorded: int
    c4xx_count: int
    c5xx_count: int
    database_status: str
    app_uptime_seconds: int
    server_time: str

