"""Shared request guards."""

from fastapi import HTTPException, Request, status

from app.services.captcha_service import captcha_service

CAPTCHA_COOKIE = "slg_human"


async def require_human(request: Request) -> None:
    """Blocks costly/abusable endpoints until the session passed the CAPTCHA.

    No-op when CAPTCHA is not configured (local development).
    """
    if not captcha_service.is_enabled():
        return
    if not captcha_service.is_valid_session_token(request.cookies.get(CAPTCHA_COOKIE)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Human verification required. Please complete the security check.",
        )
