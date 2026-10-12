"""Feedback & Reviews API routes (Section 24).
Persists user reviews to SQLite and supports server-verified CAPTCHA.
"""

from typing import List
from app.security import require_human
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.feedback import FeedbackItem, FeedbackCreateRequest, FeedbackMultiCreateRequest
from app.services.storage_service import storage_service
from app.services.captcha_service import captcha_service

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


@router.get("", response_model=List[FeedbackItem])
async def list_feedback():
    """List all submitted user feedback and reviews."""
    return storage_service.list_feedback()


@router.post("", response_model=FeedbackItem, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_human)])
async def create_feedback(req: FeedbackCreateRequest):
    """Submit a new review/feedback."""
    # Optional CAPTCHA check if token provided or required
    if req.captcha_token:
        res = await captcha_service.verify_token(req.captcha_token)
        if not res.get("success"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CAPTCHA verification failed."
            )

    try:
        item = storage_service.create_feedback(
            rating=req.rating,
            comment=req.comment,
            service_used=req.service_used
        )
        return item
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )


@router.post("/multi", response_model=List[FeedbackItem], status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_human)])
async def create_feedback_multi(req: FeedbackMultiCreateRequest):
    """Submit ONE review for several services: the same rating and comment is
    saved once per selected service so it also appears under each service filter."""
    services = []
    for name in req.services:
        clean = (name or "").strip()
        if clean and clean not in services:
            services.append(clean)
    if not services:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select at least one service to review.",
        )
    try:
        return [
            storage_service.create_feedback(rating=req.rating, comment=req.comment, service_used=svc)
            for svc in services
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )
