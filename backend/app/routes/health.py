"""Health check route (Section 23).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/health", tags=["Health"])


@router.get("")
async def health_check():
    """Return health status and service identifier."""
    return {
        "status": "ok",
        "service": "smart-local-guide"
    }
