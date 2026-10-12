"""Pydantic models for 24/7 Medical Care API contracts (Section 50.7 & Section 12).
"""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field
from app.models.places import Center, Place


class MedicalFacility(Place):
    service_type: str
    is_24_7: Optional[bool] = None


class MedicalSearchRequest(BaseModel):
    location: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0)
    service_types: Optional[List[str]] = None
    radius_km: float = Field(5.0, ge=0.1, le=50.0)
    limit: int = Field(30, ge=1, le=100)


class MedicalSearchResponse(BaseModel):
    center: Center
    radius_km: float
    total: int
    counts_by_service_type: Dict[str, int]
    emergency_disclaimer: str
    data_mode: Literal["mock", "live"]
    medical: List[MedicalFacility]
