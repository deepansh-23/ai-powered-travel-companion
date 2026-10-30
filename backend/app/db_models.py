"""PostgreSQL tables (SQLAlchemy 2). Portable types so tests can run on SQLite."""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(30))
    username_lower: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    recovery_code_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    """A logged-in browser. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_agent: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class LoginAttempt(Base):
    """Failed/successful sign-in attempts, used for the temporary lockout."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username_lower: Mapped[str] = mapped_column(String(30), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# JSONB on PostgreSQL, plain JSON elsewhere (tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class History(Base):
    """A finished search/itinerary a user can open again from the History page."""

    __tablename__ = "history"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    feature_type: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    preview: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Feedback(Base):
    """A review or user feedback. user_id is NULL for anonymous feedback."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text)
    service_used: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SavedSession(Base):
    """A half-finished page (for example an itinerary in step 3) saved to resume later."""

    __tablename__ = "saved_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(300))
    state: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, index=True)


class AppSetting(Base):
    """Application settings persisted in PostgreSQL."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ActivityDaily(Base):
    """Usage counters for the admin analytics: one small row per person (or guest), per day, per feature.

    No request contents, IP addresses or personal data are stored. Rows older than a year are pruned.
    """

    __tablename__ = "activity_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(40), primary_key=True)   # user id, or a hash for a guest
    feature: Mapped[str] = mapped_column(String(20), primary_key=True)    # visit, itinerary, area, cafes, medical, places
    kind: Mapped[str] = mapped_column(String(12), index=True)             # registered | guest
    count: Mapped[int] = mapped_column(Integer, default=0)


class AccountDeletionRequest(Base):
    """A user asked an admin to delete their account (status: pending, then removed on approval or dismissed)."""

    __tablename__ = "account_deletion_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiUsageDaily(Base):
    """Daily totals of calls to the AI model and to external APIs, for the admin usage and cost monitor.

    One row per day, provider, model/endpoint, feature and outcome. No prompts, responses, keys, user ids or IP
    addresses are stored. Rows older than a year are pruned.
    """

    __tablename__ = "api_usage_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), primary_key=True)    # gemini, serpapi, geoapify, railradar, osrm, recaptcha
    model: Mapped[str] = mapped_column(String(60), primary_key=True)       # AI model name, or the endpoint / engine called
    feature: Mapped[str] = mapped_column(String(20), primary_key=True)     # itinerary, area, cafes, medical, places, other
    outcome: Mapped[str] = mapped_column(String(8), primary_key=True)      # ok | error
    requests: Mapped[int] = mapped_column(Integer, default=0)
    total_ms: Mapped[int] = mapped_column(Integer, default=0)
    max_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)


class ItineraryUsage(Base):
    """How many itineraries each account generated in a calendar month (UTC), for the monthly limit.

    One tiny row per account per month. Only a count is kept: no trip details.
    """

    __tablename__ = "itinerary_usage"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)        # "2026-11"
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
