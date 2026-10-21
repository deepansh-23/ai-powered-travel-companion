"""Pydantic models for Itinerary Planner (Section 8 & Section 23).
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator


_LOCAL_MODES = ("walking", "public", "taxi")


def normalize_transport_modes(values):
    """['Walking', 'driving'] -> ['walking', 'taxi'] (known modes only, fixed order); None stays None."""
    if values is None:
        return None
    mapped = {"driving": "taxi", "walk": "walking", "transit": "public"}
    wanted = {mapped.get(str(v).strip().lower(), str(v).strip().lower()) for v in values}
    clean = [m for m in _LOCAL_MODES if m in wanted]
    return clean or None


class ItineraryRequest(BaseModel):
    destination: str = Field(..., min_length=2, description="Target city or destination")
    source: Optional[str] = Field(None, description="Starting origin city")
    departure_date: Optional[str] = Field(None, description="Trip start/departure date YYYY-MM-DD")
    return_date: Optional[str] = Field(None, description="Trip end/return date YYYY-MM-DD")
    selected_outbound_transport: Optional[Dict[str, Any]] = Field(None, description="Selected outbound flight/train")
    selected_return_transport: Optional[Dict[str, Any]] = Field(None, description="Selected return flight/train")
    selected_hotel: Optional[Dict[str, Any]] = Field(None, description="Selected hotel from SerpApi")
    neighborhood: Optional[str] = None
    duration_days: int = Field(3, ge=1, le=14)
    budget_per_person_per_day: float = Field(3000, ge=1000, le=100000)
    travel_group_type: str = "solo"
    travelers_count: int = Field(1, ge=1, le=20)
    rooms: Optional[int] = Field(None, ge=1, le=10, description="Hotel rooms; defaults to one per two travellers")
    radius_km: float = Field(5.0, ge=1.0, le=50.0)
    interests: List[str] = Field(default_factory=list)
    food_type: str = "no-preference"
    food_preferences: List[str] = Field(default_factory=list)
    pace: str = "moderate"
    transportation: str = "public"
    transport_modes: Optional[List[str]] = Field(
        None, description="Local transport the traveller accepts: any of walking, public, taxi")

    @field_validator("transport_modes", mode="before")
    @classmethod
    def _clean_modes(cls, v):
        return normalize_transport_modes(v)
    additional_preferences: Optional[str] = None
    # Multi-area trips (country / state / city + nearby places)
    areas: List[str] = Field(default_factory=list, description="Places to stay in, in visiting order")
    scope_kind: Optional[Literal["city", "state", "country", "area"]] = None
    arrival_city: Optional[str] = Field(None, description="City where the traveller lands (state/country trips)")
    area_schedule: Optional[List[str]] = Field(None, description="Set by the server: the area for every day")
    selected_hotels: Optional[List[Dict[str, Any]]] = None


class ItineraryPlaceItem(BaseModel):
    name: str
    category: str
    address: Optional[str] = None
    duration: Optional[str] = None
    admission: Optional[str] = None
    about: Optional[str] = Field(None, description="1-2 friendly sentences: what the place is and why people visit")
    what_to_do: Optional[str] = Field(None, description="What to do or see there")
    verified: bool = True
    website: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    directions: Optional[Dict[str, Any]] = None


class ItinerarySegment(BaseModel):
    time_window: str
    title: str
    description: str
    places: List[ItineraryPlaceItem] = Field(default_factory=list)
    transport_note: Optional[str] = None


class FoodStop(BaseModel):
    name: str
    cuisine: str
    address: Optional[str] = None
    price_level: str = "££"
    recommendation: str
    website: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    directions: Optional[Dict[str, Any]] = None


class ItineraryDay(BaseModel):
    day_number: int
    theme: str
    estimated_day_cost: str
    morning: ItinerarySegment
    food_stop_lunch: FoodStop
    afternoon: ItinerarySegment
    food_stop_dinner: FoodStop
    evening: ItinerarySegment
    area: Optional[str] = Field(None, description="Where this day is spent (multi-area trips)")
    notes: List[Dict[str, Any]] = Field(default_factory=list, description="Arrival, departure and hotel-change cards")


class ItineraryResponse(BaseModel):
    title: str
    destination: str
    source: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    selected_outbound_transport: Optional[Dict[str, Any]] = None
    selected_return_transport: Optional[Dict[str, Any]] = None
    selected_hotel: Optional[Dict[str, Any]] = None
    cost_breakdown: Optional[Dict[str, Any]] = None
    duration_days: int
    estimated_budget_total: str
    currency: str
    pace: str
    trip_overview: str
    days: List[ItineraryDay]
    sources: List[str]
    disclaimer: str
    data_mode: Literal["mock", "live"]
    areas: List[str] = Field(default_factory=list)
    stay_blocks: List[Dict[str, Any]] = Field(default_factory=list, description="Groups of days that share one hotel")
    transfers: List[Dict[str, Any]] = Field(default_factory=list, description="Estimated travel between stays")
    selected_hotels: Optional[List[Dict[str, Any]]] = None
    notices: List[str] = Field(default_factory=list)


class ScopeRequest(BaseModel):
    destination: str = Field(..., min_length=2)
    kind: Optional[Literal["city", "state", "country", "area"]] = None
    duration_days: int = Field(3, ge=1, le=14)


class ScopeResponse(BaseModel):
    kind: Literal["city", "state", "country", "area"]
    name: str
    advice: str
    recommended_areas: int
    modes: List[Dict[str, str]] = Field(default_factory=list)
    suggestions: List[Dict[str, str]] = Field(default_factory=list)
    suggestions_title: str = ""
    neighbours: List[Dict[str, str]] = Field(default_factory=list)
    neighbours_title: str = ""
    needs_arrival: bool = False
    default_arrival: Optional[str] = Field(None, description="Suggested landing city (capital or main-airport city)")
    default_arrival_note: str = ""
    arrival_options: List[Dict[str, str]] = Field(default_factory=list, description="Cities the traveller can start from")
    source: Literal["ai", "static", "basic"] = "basic"


class StayHotelChoice(BaseModel):
    block_index: int = Field(..., ge=0)
    hotel: Optional[Dict[str, Any]] = None


class TransferChoice(BaseModel):
    """How the traveller moves between two stays (mode: flight, train, cab or other)."""
    to_stay: int = Field(..., ge=0)
    mode: Literal["flight", "train", "cab", "other"]
    option: Optional[Dict[str, Any]] = None


class FinalizeRequest(BaseModel):
    itinerary: ItineraryResponse
    stay_hotels: List[StayHotelChoice] = Field(default_factory=list)
    travelers_count: int = Field(1, ge=1, le=20)
    rooms: Optional[int] = Field(None, ge=1, le=10)
    budget_per_person_per_day: float = Field(3000, ge=1000, le=100000)
    transportation: str = "public"
    transport_modes: Optional[List[str]] = None
    transfer_choices: List[TransferChoice] = Field(default_factory=list)

    @field_validator("transport_modes", mode="before")
    @classmethod
    def _clean_modes(cls, v):
        return normalize_transport_modes(v)

