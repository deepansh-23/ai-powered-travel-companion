"""Reviews API: anyone can read; posting needs a login (the review shows the username) AND a CAPTCHA tick,
so scripts cannot fill the review section with spam."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db_models import User
from app.models.feedback import FeedbackCreateRequest, FeedbackItem, FeedbackMultiCreateRequest
from app.security import require_same_origin, require_user
from app.services import repository
from app.services.captcha_service import enforce_captcha
from app.services.site_settings_guard import require_setting

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("", response_model=List[FeedbackItem])
async def list_feedback(db: AsyncSession = Depends(get_db)):
    """List all submitted reviews (public)."""
    return await repository.list_feedback(db)


@router.post("", response_model=FeedbackItem, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_same_origin)])
async def create_feedback(req: FeedbackCreateRequest, request: Request, user: User = Depends(require_user),
                          db: AsyncSession = Depends(get_db)):
    await require_setting("allow_reviews", "New reviews are temporarily disabled.")
    await enforce_captcha(req.captcha_token, _client_ip(request), "post your review")
    try:
        return await repository.create_feedback(db, user, req.rating, req.comment, req.service_used)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/multi", response_model=List[FeedbackItem], status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_same_origin)])
async def create_feedback_multi(req: FeedbackMultiCreateRequest, request: Request, user: User = Depends(require_user),
                                db: AsyncSession = Depends(get_db)):
    """ONE review for several services: saved once per selected service (same rating and comment)."""
    await require_setting("allow_reviews", "New reviews are temporarily disabled.")
    await enforce_captcha(req.captcha_token, _client_ip(request), "post your review")
    services: List[str] = []
    for name in req.services:
        clean = (name or "").strip()
        if clean and clean not in services:
            services.append(clean)
    if not services:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Select at least one service to review.")
    try:
        return [await repository.create_feedback(db, user, req.rating, req.comment, svc) for svc in services]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
