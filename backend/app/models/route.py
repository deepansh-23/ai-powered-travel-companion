"""Pydantic model for routing API contracts (Section 50.7).
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude between -90 and 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude between -180 and 180")


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate
    mode: Literal["walking", "driving"] = "walking"


class RouteResponse(BaseModel):
    geometry: dict = Field(..., description="GeoJSON LineString geometry")
    distance_m: int = Field(..., description="Calculated route distance in meters")
    duration_s: Optional[int] = Field(None, description="Travel duration in seconds (null if approximate)")
    mode: str = Field(..., description="Route travel mode")
    provider: str = Field(..., description="Routing service provider or fallback identifier")
    is_approximate: bool = Field(False, description="True if fallback straight-line route")
    summary: str = Field(..., description="Human-readable route summary")
