"""Pydantic models for Quiet Work Cafes API contracts (Section 50.7 & Section 11).
"""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field
from app.models.places import Center, Place


class Cafe(Place):
    amenities: List[str] = Field(default_factory=list)


class CafesSearchRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    amenities: Optional[List[str]] = None
    radius_km: float = Field(3.0, ge=0.1, le=50.0)
    limit: int = Field(30, ge=1, le=100)


class CafesSearchResponse(BaseModel):
    center: Center
    radius_km: float
    total: int
    counts_by_amenity: Dict[str, int]
    data_mode: Literal["mock", "live"]
    cafes: List[Cafe]
