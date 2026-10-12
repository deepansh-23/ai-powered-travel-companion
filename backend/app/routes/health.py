"""Health check route (Section 23).
"""

from fastapi import APIRouter

from app.db import db_status

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("")
async def health_check():
    """Return health status and service identifier."""
    return {
        "status": "ok",
        "service": "smart-local-guide",
        "database": {"configured": db_status()["configured"], "ready": db_status()["ready"]}
    }
