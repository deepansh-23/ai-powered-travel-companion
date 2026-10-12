"""History management API routes (Section 13 & 23).
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status
from app.models.history import HistoryItem, HistoryCreateRequest
from app.services.storage_service import storage_service

router = APIRouter(prefix="/api/history", tags=["History"])


@router.get("", response_model=List[HistoryItem])
async def list_history(feature_type: Optional[str] = None):
    """Retrieve history items, optionally filtered by feature category."""
    items = storage_service.list_history(feature_type=feature_type)
    return items


@router.post("", response_model=HistoryItem, status_code=status.HTTP_201_CREATED)
async def create_history_item(req: HistoryCreateRequest):
    """Create a new history record stored persistently."""
    item = storage_service.create_history(
        feature_type=req.feature_type,
        title=req.title,
        preview=req.preview,
        payload=req.payload
    )
    return item


@router.delete("/{item_id}")
async def delete_history_item(item_id: str):
    """Delete a history record by ID."""
    success = storage_service.delete_history(item_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"History item '{item_id}' not found."
        )
    return {"status": "deleted", "id": item_id}

