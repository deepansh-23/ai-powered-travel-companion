"""Saved sessions (drafts): resume a half-finished page later."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SessionSaveRequest(BaseModel):
    id: Optional[str] = Field(None, description="Existing draft to overwrite; omit to create a new one")
    service: str = Field(..., max_length=30)
    title: str = Field(..., min_length=1, max_length=300)
    state: Dict[str, Any] = Field(default_factory=dict)


class SessionMeta(BaseModel):
    id: str
    service: str
    title: str
    created_at: str
    updated_at: str


class SessionFull(SessionMeta):
    state: Dict[str, Any] = Field(default_factory=dict)
