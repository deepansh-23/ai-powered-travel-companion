"""Pydantic models for Places Near You API contracts (Section 50.7).
"""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


class Center(BaseModel):
    latitude: float
    longitude: float
    label: str
    kind: Literal["user_location", "search_area"]


class Place(BaseModel):
    id: str
    name: str
    category: str
    description: str
    description_source: Literal["provider", "generated_template", "ai"] = "provider"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_m: Optional[int] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    rating_source: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    source: str = "sample-data"


class PlacesSearchRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    categories: Optional[List[str]] = None
    radius_km: float = Field(3.0, ge=0.1, le=50.0)
    limit: int = Field(30, ge=1, le=100)


class PlacesSearchResponse(BaseModel):
    center: Center
    radius_km: float
    total: int
    counts_by_category: Dict[str, int]
    data_mode: Literal["mock", "live"]
    places: List[Place]
