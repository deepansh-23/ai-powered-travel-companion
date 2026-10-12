"""Automated tests verifying external booking links are strictly provider-supplied (Section 33A-8).
Never invented or synthesized in backend code.
"""

from app.services.flight_service import flight_service
from app.services.hotel_service import hotel_service


def test_flight_booking_link_only_from_provider():
    raw_data_no_link = {
        "best_flights": [
            {
                "flights": [
                    {
                        "departure_airport": {"id": "DEL", "time": "10:00"},
                        "arrival_airport": {"id": "BOM", "time": "12:00"},
                        "airline": "Vistara",
                        "flight_number": "UK 991"
                    }
                ],
                "total_duration": 120,
                "price": 4200
                # No booking_options and no link!
            }
        ]
    }
    options = flight_service.parse_serpapi_flights(raw_data_no_link)
    assert len(options) == 1
    # booking_url must be None/null, never constructed
    assert options[0].booking_url is None


def test_hotel_booking_link_only_from_provider():
    raw_hotel_no_link = {
        "properties": [
            {
                "name": "Standard Guest House",
                "rate_per_night": {"lowest": 1500},
                # No link and no price sources
            }
        ]
    }
    hotels = hotel_service.parse_serpapi_hotels(raw_hotel_no_link, "2026-10-15", "2026-10-16")
    assert len(hotels) == 1
    assert hotels[0].booking_url is None
