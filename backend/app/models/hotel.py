"""Normalized Hotel models for SerpApi Google Hotels (Section 7A, 31).
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class HotelPriceSource(BaseModel):
    source_name: str = Field(..., description="Booking provider or site name, e.g. Booking.com, Agoda")
    price: float = Field(..., description="Quoted rate from this provider")
    currency: str = Field("INR", description="Currency symbol or code")
    is_cheapest: bool = False
    booking_url: Optional[str] = Field(None, description="Provider-supplied direct booking or search link")


class HotelOption(BaseModel):
    id: str
    provider: Literal["serpapi_google_hotels", "geoapify_fallback"] = "serpapi_google_hotels"
    name: str = Field(..., description="Hotel name")
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    star_class: Optional[int] = Field(None, ge=1, le=5, description="Hotel star rating")
    rating: Optional[float] = Field(None, ge=0.0, le=5.0, description="Guest rating out of 5")
    review_count: Optional[int] = Field(None, ge=0)
    nightly_price: Optional[float] = None
    total_price: Optional[float] = None
    currency: str = "INR"
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    free_cancellation: Optional[bool] = None
    amenities: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    price_sources: List[HotelPriceSource] = Field(default_factory=list)
    booking_url: Optional[str] = Field(None, description="Provider-supplied booking URL only")
    recommendation_labels: List[str] = Field(default_factory=list, description="Computed labels e.g. Cheapest, Best Rated, Best Value")
    recommendation_reason: Optional[str] = None
    price_status: Literal["live_quote", "unpriced_fallback"] = "live_quote"
    raw_provider_data: Optional[Dict[str, Any]] = None


class HotelSearchRequest(BaseModel):
    destination: str = Field(..., min_length=2, description="Target city for hotel search")
    check_in_date: str = Field(..., description="YYYY-MM-DD check-in date")
    check_out_date: str = Field(..., description="YYYY-MM-DD check-out date")
    travelers: int = Field(1, ge=1, le=20)
    currency: str = "INR"
    sort_by: Literal["lowest_price", "highest_rating", "most_reviewed", "relevance"] = "relevance"
    min_rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    min_price: Optional[float] = Field(None, ge=0.0)
    max_price: Optional[float] = Field(None, ge=0.0)
    star_class: Optional[int] = Field(None, ge=1, le=5)
    free_cancellation: Optional[bool] = None


class HotelDetailsRequest(BaseModel):
    property_token: str = Field(..., description="SerpApi property token or hotel identifier")
    check_in_date: str
    check_out_date: str
    currency: str = "INR"
    adults: int = 1


class HotelSearchResponse(BaseModel):
    destination: str
    check_in_date: str
    check_out_date: str
    hotels: List[HotelOption] = Field(default_factory=list)
    total_found: int = 0
    disclaimer: str = "Provider prices are live quotes, not booking guarantees. Check availability before travel."
