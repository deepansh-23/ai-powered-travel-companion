"""Public application settings endpoint.

Returns safe user-facing settings (maintenance mode status, announcement banner, etc.).
Never returns API keys, secrets, or administrative data.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import db_status, get_db
from admin.schemas import PublicSettingsResponse
from admin.service import get_settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("/public", response_model=PublicSettingsResponse)
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    """Return non-secret application settings for the public website."""
    if not db_status()["ready"]:
        # Safe offline defaults if DB is temporarily disconnected
        return PublicSettingsResponse(
            maintenance_mode=False,
            public_notice_enabled=False,
            public_notice_text="",
            guest_mode_enabled=True,
            allow_registration=True,
            allow_reviews=True,
        )

    try:
        data = await get_settings(db)
        return PublicSettingsResponse(
            maintenance_mode=data.get("maintenance_mode", False),
            public_notice_enabled=data.get("public_notice_enabled", False),
            public_notice_text=data.get("public_notice_text", ""),
            guest_mode_enabled=data.get("guest_mode_enabled", True),
            allow_registration=data.get("allow_registration", True),
            allow_reviews=data.get("allow_reviews", True),
        )
    except Exception:
        return PublicSettingsResponse(
            maintenance_mode=False,
            public_notice_enabled=False,
            public_notice_text="",
            guest_mode_enabled=True,
            allow_registration=True,
            allow_reviews=True,
        )
