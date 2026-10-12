"""History management API routes: every record belongs to the logged-in user."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db_models import User
from app.models.history import HistoryCreateRequest, HistoryItem
from app.security import require_same_origin, require_user
from app.services import repository

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("", response_model=List[HistoryItem])
async def list_history(feature_type: Optional[str] = None, user: User = Depends(require_user),
                       db: AsyncSession = Depends(get_db)):
    """Only the logged-in user's own history, optionally filtered by feature."""
    return await repository.list_history(db, user.id, feature_type)


@router.post("", response_model=HistoryItem, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_same_origin)])
async def create_history_item(req: HistoryCreateRequest, user: User = Depends(require_user),
                              db: AsyncSession = Depends(get_db)):
    return await repository.create_history(db, user.id, req.feature_type, req.title, req.preview, req.payload)


@router.delete("/{item_id}", dependencies=[Depends(require_same_origin)])
async def delete_history_item(item_id: str, user: User = Depends(require_user),
                              db: AsyncSession = Depends(get_db)):
    if not await repository.delete_history(db, user.id, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"History item '{item_id}' not found.")
    return {"status": "deleted", "id": item_id}
