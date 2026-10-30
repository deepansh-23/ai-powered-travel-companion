"""CAPTCHA verification routes (Section 25).
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import settings
from app.security import CAPTCHA_COOKIE
from app.services.captcha_service import captcha_service

router = APIRouter(prefix="/api/captcha", tags=["CAPTCHA"])
logger = logging.getLogger(__name__)
_warned_problems = set()          # each configuration problem is logged once, not on every page load


class CaptchaVerifyRequest(BaseModel):
    token: Optional[str] = None


@router.get("/config")
async def get_captcha_config():
    """Public config only: site key, provider and script URL. Never the secret."""
    enabled = captcha_service.is_enabled()
    problem = captcha_service.config_problem()
    if problem and problem not in _warned_problems:
        _warned_problems.add(problem)
        logger.warning("CAPTCHA configuration: %s", problem)
    return {
        "enabled": enabled,
        "site_key": settings.RECAPTCHA_SITE_KEY if enabled else "",
        "provider": settings.CAPTCHA_PROVIDER,
        "script_url": captcha_service.provider()["script_url"] if enabled else "",
    }


@router.get("/status")
async def get_captcha_status(request: Request):
    """Whether this browser session already passed human verification."""
    if not captcha_service.is_enabled():
        return {"enabled": False, "verified": True}
    token = request.cookies.get(CAPTCHA_COOKIE)
    return {"enabled": True, "verified": captcha_service.is_valid_session_token(token)}


@router.post("/verify")
async def verify_captcha(req: CaptchaVerifyRequest, request: Request, response: Response):
    """Server-side verification of the client CAPTCHA token, then start the session."""
    client_ip = request.client.host if request.client else None
    result = await captcha_service.verify_token(req.token, remote_ip=client_ip)
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "CAPTCHA verification failed. Please try again.")
        )
    if captcha_service.is_enabled():
        response.set_cookie(
            CAPTCHA_COOKIE,
            captcha_service.issue_session_token(),
            max_age=int(settings.CAPTCHA_SESSION_HOURS) * 3600,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        )
    return {"status": "verified", "detail": "Human verification successful."}
