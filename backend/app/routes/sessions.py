"""Saved sessions API: a logged-in user's own drafts only."""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db_models import User
from app.models.sessions import SessionFull, SessionMeta, SessionSaveRequest
from app.security import require_same_origin, require_user
from app.services import repository

router = APIRouter(prefix="/api/sessions", tags=["Saved sessions"])

MAX_STATE_BYTES = 2_000_000


@router.get("", response_model=List[SessionMeta])
async def list_sessions(service: Optional[str] = None, user: User = Depends(require_user),
                        db: AsyncSession = Depends(get_db)):
    return await repository.list_sessions(db, user.id, service)


@router.get("/{session_id}", response_model=SessionFull)
async def get_session(session_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    item = await repository.get_session(db, user.id, session_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved session not found.")
    return item


@router.post("", response_model=SessionMeta, dependencies=[Depends(require_same_origin)])
async def save_session(req: SessionSaveRequest, user: User = Depends(require_user),
                       db: AsyncSession = Depends(get_db)):
    if req.service not in repository.SESSION_SERVICES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown service.")
    if len(json.dumps(req.state)) > MAX_STATE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "This session is too large to save.")
    try:
        return await repository.save_session(db, user.id, req.service, req.title, req.state, req.id)
    except repository.SessionLimitReached as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.delete("/{session_id}", dependencies=[Depends(require_same_origin)])
async def delete_session(session_id: str, user: User = Depends(require_user), db: AsyncSession = Depends(get_db)):
    if not await repository.delete_session(db, user.id, session_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved session not found.")
    return {"status": "deleted", "id": session_id}
