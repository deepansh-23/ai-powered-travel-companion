"""Admin authorization dependency.

All admin endpoints must depend on `require_admin`.
Authorization is fully server-side — no frontend role value is trusted.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db_models import User
from app.security import require_same_origin
from app.services import auth_service
from app.config import settings


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """FastAPI dependency: allow only authenticated admin users.

    - Unauthenticated → 401
    - Authenticated non-admin → 403
    - Active admin → returns User
    """
    user = await auth_service.get_user_for_token(db, request.cookies.get(settings.AUTH_COOKIE_NAME))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    if not getattr(user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
