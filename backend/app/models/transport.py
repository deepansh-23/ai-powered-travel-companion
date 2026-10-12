"""Normalized transport models for Flights and Trains (Section 6, 7, 31).
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class TransportOption(BaseModel):
    id: str
    mode: Literal["flight", "train"]
    provider: Literal["serpapi_google_flights", "railradar"]
    operator: str = Field(..., description="Airline or Railway operator name")
    number: Optional[str] = Field(None, description="Flight or Train number")
    origin: str = Field(..., description="Departure airport or station code/name")
    destination: str = Field(..., description="Arrival airport or station code/name")
    departure_time: str = Field(..., description="Departure date and time formatted string")
    arrival_time: str = Field(..., description="Arrival date and time formatted string")
    duration_minutes: int = Field(..., ge=1, description="Total journey time in minutes")
    duration_formatted: Optional[str] = None
    stops: int = Field(0, ge=0, description="Number of stops/layovers")
    layover_details: Optional[str] = None
    price: Optional[float] = Field(None, description="Ticket fare amount")
    currency: str = Field("INR", description="Currency symbol/code")
    cabin_or_class: Optional[str] = Field("Economy", description="Cabin class or coach class")
    booking_url: Optional[str] = Field(None, description="Legitimate provider-supplied booking URL only")
    score: Optional[float] = None
    recommendation_badge: Optional[str] = None
    recommendation_reason: Optional[str] = None
    price_insight: Optional[str] = None
    raw_provider_data: Optional[Dict[str, Any]] = None


class TransportSearchRequest(BaseModel):
    source: str = Field(..., min_length=2, description="Departure city or station/airport")
    destination: str = Field(..., min_length=2, description="Arrival city or station/airport")
    outbound_date: str = Field(..., description="YYYY-MM-DD outbound departure date")
    return_date: Optional[str] = Field(None, description="YYYY-MM-DD return departure date")
    travelers: int = Field(1, ge=1, le=20, description="Number of passengers")
    preference: Literal[
        "cheapest", "fastest", "best-overall", "prefer-flight", "prefer-train", "no-preference"
    ] = "best-overall"
    currency: str = "INR"


class TransportLegResult(BaseModel):
    flights: List[TransportOption] = Field(default_factory=list)
    trains: List[TransportOption] = Field(default_factory=list)
    top_recommendation: Optional[TransportOption] = None
    airport_notice: Optional[str] = None
    rail_notice: Optional[str] = None


class TransportSearchResponse(BaseModel):
    source: str
    destination: str
    outbound: TransportLegResult
    return_leg: Optional[TransportLegResult] = None
    preference: str
