"""Pydantic models for User Feedback and Reviews (Section 24).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class FeedbackItem(BaseModel):
    id: str
    rating: int = Field(..., ge=1, le=5)
    comment: str
    service_used: Optional[str] = None
    created_at: str
    username: Optional[str] = None  # reviewer (None for old anonymous reviews)


class FeedbackCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    comment: str = Field(..., min_length=2, max_length=2000, description="User review/comment")
    service_used: Optional[str] = Field(None, description="Service reviewed (e.g. Itinerary, Places, etc.)")
    captcha_token: Optional[str] = Field(None, description="reCAPTCHA verification token")


class FeedbackMultiCreateRequest(BaseModel):
    """One review that applies to several services at once."""
    rating: int = Field(..., ge=1, le=5, description="1 to 5 star rating")
    comment: str = Field(..., min_length=2, max_length=2000, description="User review/comment")
    services: List[str] = Field(..., min_length=1, max_length=10, description="Services this review covers")
