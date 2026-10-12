"""Automated tests for SerpApi Google Flights parsing and normalization (Section 33A-1).
Uses saved fixtures and mocked HTTP; never calls paid live APIs.
"""

import pytest
from app.services.flight_service import flight_service, resolve_city_to_airports

SAMPLE_SERPAPI_FLIGHTS = {
    "best_flights": [
        {
            "flights": [
                {
                    "departure_airport": {"name": "Indira Gandhi International", "id": "DEL", "time": "2026-10-15 06:15"},
                    "arrival_airport": {"name": "Sri Guru Ram Dass Jee", "id": "ATQ", "time": "2026-10-15 07:25"},
                    "duration": 70,
                    "airplane": "Airbus A320",
                    "airline": "IndiGo",
                    "airline_logo": "https://example.com/indigo.png",
                    "travel_class": "Economy",
                    "flight_number": "6E 2045",
                    "legroom": "29 in"
                }
            ],
            "total_duration": 70,
            "price": 3850,
            "type": "One way",
            "booking_options": [
                {"book_with": "IndiGo", "link": "https://www.goindigo.in/booking/details?ref=provider_supplied"}
            ]
        }
    ],
    "other_flights": [
        {
            # Duplicate of the best flight with same flight number and time
            "flights": [
                {
                    "departure_airport": {"name": "Indira Gandhi International", "id": "DEL", "time": "2026-10-15 06:15"},
                    "arrival_airport": {"name": "Sri Guru Ram Dass Jee", "id": "ATQ", "time": "2026-10-15 07:25"},
                    "duration": 70,
                    "airline": "IndiGo",
                    "flight_number": "6E 2045"
                }
            ],
            "total_duration": 70,
            "price": 3850
        },
        {
            # Second unique flight with 1 stop/layover
            "flights": [
                {
                    "departure_airport": {"name": "Indira Gandhi International", "id": "DEL", "time": "2026-10-15 09:00"},
                    "arrival_airport": {"name": "Chandigarh Airport", "id": "IXC", "time": "2026-10-15 09:55"},
                    "duration": 55,
                    "airline": "Air India",
                    "flight_number": "AI 463"
                },
                {
                    "departure_airport": {"name": "Chandigarh Airport", "id": "IXC", "time": "2026-10-15 11:30"},
                    "arrival_airport": {"name": "Sri Guru Ram Dass Jee", "id": "ATQ", "time": "2026-10-15 12:20"},
                    "duration": 50,
                    "airline": "Air India",
                    "flight_number": "AI 464"
                }
            ],
            "layovers": [
                {"name": "Chandigarh Airport", "id": "IXC", "duration": 95}
            ],
            "total_duration": 200,
            "price": 5200,
            "link": "https://www.airindia.com/flight-details?flight=AI463"
        }
    ]
}


def test_parse_serpapi_flights():
    options = flight_service.parse_serpapi_flights(SAMPLE_SERPAPI_FLIGHTS, currency="INR")

    # Verify merging best and other without duplicate (3 raw items -> 2 unique options)
    assert len(options) == 2

    # Verify first option
    opt1 = options[0]
    assert opt1.operator == "IndiGo"
    assert opt1.number == "6E 2045"
    assert "DEL" in opt1.origin
    assert "ATQ" in opt1.destination
    assert opt1.departure_time == "2026-10-15 06:15"
    assert opt1.arrival_time == "2026-10-15 07:25"
    assert opt1.duration_minutes == 70
    assert opt1.duration_formatted == "1h 10m"
    assert opt1.stops == 0
    assert opt1.price == 3850.0
    assert opt1.currency == "INR"
    assert opt1.booking_url == "https://www.goindigo.in/booking/details?ref=provider_supplied"

    # Verify second option with layover
    opt2 = options[1]
    assert opt2.operator == "Air India"
    assert opt2.number == "AI 463"
    assert opt2.stops == 1
    assert "IXC" in opt2.layover_details
    assert opt2.duration_minutes == 200
    assert opt2.duration_formatted == "3h 20m"
    assert opt2.price == 5200.0
    assert opt2.booking_url == "https://www.airindia.com/flight-details?flight=AI463"


def test_city_resolution_airport():
    # Known cities
    codes, notice = resolve_city_to_airports("Delhi")
    assert codes == ["DEL"]
    assert notice is None

    codes, notice = resolve_city_to_airports("Amritsar")
    assert codes == ["ATQ"]
    assert notice is None

    codes, notice = resolve_city_to_airports("Goa")
    assert "GOI" in codes or "GOX" in codes
    assert notice is None

    # City with no commercial airport
    codes, notice = resolve_city_to_airports("Rishikesh")
    assert codes == []
    assert notice is not None
    assert "No commercial airport" in notice

    # Direct IATA code pass-through
    codes, notice = resolve_city_to_airports("BOM")
    assert codes == ["BOM"]
    assert notice is None


def test_airport_resolution_exact_and_multi_airport():
    from app.services.flight_service import resolve_city_to_airports

    assert resolve_city_to_airports("Goa")[0] == ["GOI", "GOX"]
    assert resolve_city_to_airports("Amritsar, Punjab, India")[0] == ["ATQ"]
    codes, notice = resolve_city_to_airports("Go")  # partial name must not match Goa
    assert codes == [] and notice
    codes, notice = resolve_city_to_airports("Rishikesh")
    assert codes == [] and "No commercial airport" in notice


def test_flight_ids_are_stable_and_booking_token_kept():
    from app.services.flight_service import flight_service

    data = {
        "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?provider=1"},
        "price_insights": {"price_level": "low", "typical_price_range": [4000, 6000]},
        "best_flights": [{
            "flights": [{
                "departure_airport": {"id": "DEL", "name": "Delhi", "time": "2026-11-10 06:00"},
                "arrival_airport": {"id": "ATQ", "name": "Amritsar", "time": "2026-11-10 07:10"},
                "airline": "IndiGo", "flight_number": "6E 123",
            }],
            "total_duration": 70, "price": 4500, "booking_token": "tok123",
        }],
    }
    a = flight_service.parse_serpapi_flights(data)
    b = flight_service.parse_serpapi_flights(data)
    assert a[0].id == b[0].id and a[0].id.startswith("flt_")
    assert a[0].raw_provider_data["booking_token"] == "tok123"
    assert a[0].booking_url == "https://www.google.com/travel/flights?provider=1"
    assert "low" in a[0].price_insight
