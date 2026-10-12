"""Pydantic models for Search/Generation History (Section 13 & Section 23).
"""

from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class HistoryItem(BaseModel):
    id: str
    feature_type: str
    title: str
    created_at: str
    preview: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class HistoryCreateRequest(BaseModel):
    feature_type: str
    title: str
    preview: str
    payload: Dict[str, Any] = Field(default_factory=dict)
