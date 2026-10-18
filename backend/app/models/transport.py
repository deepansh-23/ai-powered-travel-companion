"""Normalized transport models for Flights and Trains (Section 6, 7, 31).
"""

import re
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

# Train classes the planner can ask about, with the friendly names shown in the UI.
TRAIN_CLASS_LABELS: Dict[str, str] = {
    "SL": "Sleeper (SL)",
    "3A": "AC 3 Tier (3AC)",
    "2A": "AC 2 Tier (2AC)",
    "1A": "AC First Class (1AC)",
}
_CLASS_ALIASES = {"SL": "SL", "3A": "3A", "3AC": "3A", "2A": "2A", "2AC": "2A", "1A": "1A", "1AC": "1A"}
_STATION_CODE_RE = re.compile(r"^[A-Z0-9]{2,6}$")


def normalize_train_classes(values: Optional[List[str]]) -> List[str]:
    """['3AC', 'sl', '3A'] -> ['SL', '3A'] (known classes only, de-duplicated, fixed order)."""
    wanted = set()
    for v in values or []:
        key = _CLASS_ALIASES.get(str(v).strip().upper())
        if key is None:
            raise ValueError(f"Unknown train class '{v}'. Choose from SL, 3AC, 2AC, 1AC.")
        wanted.add(key)
    return [c for c in TRAIN_CLASS_LABELS if c in wanted]


def normalize_station_code(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    code = str(value).strip().upper()
    if not _STATION_CODE_RE.match(code):
        raise ValueError(f"'{value}' is not a valid railway station code.")
    return code


class TrainClassInfo(BaseModel):
    """One class (SL/3A/2A/1A) on one train. Fare/availability stay None unless a provider supplied them."""
    code: str
    label: str
    offered: Optional[bool] = Field(None, description="Does this train carry this class? None = could not be verified")
    fare_per_person: Optional[float] = None
    availability_status: Optional[Literal["AVAILABLE", "RAC", "WL"]] = None
    availability_detail: Optional[str] = Field(None, description="Provider text such as 'AVAILABLE 45' or 'WL 12'")
    data_quality: Literal["verified", "unavailable"] = "unavailable"
    note: Optional[str] = None


class TrainFareAvailability(BaseModel):
    classes: List[TrainClassInfo] = Field(default_factory=list)
    fares_supported: bool = False
    availability_supported: bool = False
    classes_verified: bool = False
    source: str = "railradar"
    notice: Optional[str] = None
    check_url: Optional[str] = Field(None, description="Official site where live fare and availability can be checked")


class TrainAdvicePick(BaseModel):
    label: str
    option_id: str
    title: str
    reasons: List[str] = Field(default_factory=list)


class TrainAdvice(BaseModel):
    headline: str
    picks: List[TrainAdvicePick] = Field(default_factory=list)
    summary: str
    source: Literal["ai", "rule-based"] = "rule-based"
    caveats: List[str] = Field(default_factory=list)


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
    fare_availability: Optional[TrainFareAvailability] = None


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
    # Optional "Additional Details for Train Travel"
    train_classes: List[str] = Field(default_factory=list, description="Preferred classes: SL, 3A, 2A, 1A")
    source_station_code: Optional[str] = Field(None, description="Chosen departure railway station code, e.g. NDLS")
    destination_station_code: Optional[str] = Field(None, description="Chosen arrival railway station code")

    @field_validator("train_classes", mode="before")
    @classmethod
    def _clean_classes(cls, v):
        return normalize_train_classes(v)

    @field_validator("source_station_code", "destination_station_code", mode="before")
    @classmethod
    def _clean_station(cls, v):
        return normalize_station_code(v)


class TransportLegResult(BaseModel):
    flights: List[TransportOption] = Field(default_factory=list)
    trains: List[TransportOption] = Field(default_factory=list)
    top_recommendation: Optional[TransportOption] = None
    airport_notice: Optional[str] = None
    rail_notice: Optional[str] = None
    train_advice: Optional[TrainAdvice] = None


class TransportSearchResponse(BaseModel):
    source: str
    destination: str
    outbound: TransportLegResult
    return_leg: Optional[TransportLegResult] = None
    preference: str


class FlightDatesRequest(BaseModel):
    origin: str = Field(..., min_length=2)
    destination: str = Field(..., min_length=2)
    date: str = Field(..., description="The currently selected travel date YYYY-MM-DD")
    earliest_date: Optional[str] = Field(None, description="Dates before this are not offered (e.g. outbound date for the return leg)")
    travelers: int = Field(1, ge=1, le=20)
    currency: str = "INR"


class FlightDatePrice(BaseModel):
    date: str
    label: str
    cheapest_price: Optional[float] = None
    tier: Literal["low", "medium", "high", "unknown"] = "unknown"
    flights_found: int = 0
    is_selected: bool = False
    is_cheapest: bool = False


class FlightDatesResponse(BaseModel):
    days: List[FlightDatePrice] = Field(default_factory=list)
    note: Optional[str] = None
    notice: Optional[str] = None
    currency: str = "INR"


class LegSearchRequest(BaseModel):
    origin: str = Field(..., min_length=2)
    destination: str = Field(..., min_length=2)
    date: str
    travelers: int = Field(1, ge=1, le=20)
    preference: Literal[
        "cheapest", "fastest", "best-overall", "prefer-flight", "prefer-train", "no-preference"
    ] = "best-overall"
    currency: str = "INR"
    train_classes: List[str] = Field(default_factory=list)
    origin_station_code: Optional[str] = None
    destination_station_code: Optional[str] = None

    @field_validator("train_classes", mode="before")
    @classmethod
    def _clean_classes(cls, v):
        return normalize_train_classes(v)

    @field_validator("origin_station_code", "destination_station_code", mode="before")
    @classmethod
    def _clean_station(cls, v):
        return normalize_station_code(v)


class StationInfo(BaseModel):
    code: str
    name: str
    city: Optional[str] = None


class StationSearchResponse(BaseModel):
    query: str
    stations: List[StationInfo] = Field(default_factory=list)
    notice: Optional[str] = None
    source: str = "railradar"
