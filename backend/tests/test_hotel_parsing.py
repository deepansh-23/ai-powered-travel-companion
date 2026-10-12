"""Automated tests for SerpApi Google Hotels parsing, normalization and price comparison (Section 33A-2).
"""

import pytest
from app.services.hotel_service import hotel_service

SAMPLE_SERPAPI_HOTELS = {
    "properties": [
        {
            "name": "Taj Swarna, Amritsar",
            "property_token": "prop_taj_123",
            "description": "Luxury 5-star hotel near Golden Temple",
            "gps_coordinates": {"latitude": 31.6521, "longitude": 74.8812},
            "overall_rating": 4.7,
            "reviews": 3200,
            "extracted_hotel_class": 5,
            "rate_per_night": {"lowest": "₹7,500", "extracted_lowest": 7500},
            "total_rate": {"lowest": "₹15,000", "extracted_lowest": 15000},
            "amenities": ["Free Wi-Fi", "Pool", "Spa", "Free cancellation", "Fitness center"],
            "images": [{"original_image": "https://example.com/taj_main.jpg"}],
            "prices": [
                {"source": "Booking.com", "rate_per_night": 7500, "link": "https://booking.com/taj"},
                {"source": "Agoda", "rate_per_night": 7800, "link": "https://agoda.com/taj"},
                {"source": "Expedia", "rate_per_night": 7950, "link": "https://expedia.com/taj"}
            ],
            "link": "https://www.google.com/travel/hotels/taj"
        },
        {
            "name": "City Heritage Inn",
            "property_token": "prop_heritage_456",
            "description": "Budget hotel 500m from heritage street",
            "gps_coordinates": {"latitude": 31.6255, "longitude": 74.8765},
            "overall_rating": 4.1,
            "reviews": 650,
            "extracted_hotel_class": 3,
            "rate_per_night": {"extracted_lowest": 2200},
            "total_rate": {"extracted_lowest": 4400},
            "amenities": ["Free Wi-Fi", "Air conditioning"],
            "link": "https://www.google.com/travel/hotels/heritage"
        }
    ]
}

SAMPLE_PROPERTY_DETAILS = {
    "prices": [
        {"source": "Booking.com", "price": 7500, "link": "https://booking.com/taj"},
        {"source": "Agoda", "price": 7250, "link": "https://agoda.com/taj_deal"},
        {"source": "Hotels.com", "price": 7600, "link": "https://hotels.com/taj"}
    ]
}


def test_parse_serpapi_hotels():
    hotels = hotel_service.parse_serpapi_hotels(
        SAMPLE_SERPAPI_HOTELS,
        check_in_date="2026-10-15",
        check_out_date="2026-10-17",
        currency="INR"
    )

    assert len(hotels) == 2

    h1 = hotels[0]
    assert h1.name == "Taj Swarna, Amritsar"
    assert h1.latitude == pytest.approx(31.6521)
    assert h1.longitude == pytest.approx(74.8812)
    assert h1.star_class == 5
    assert h1.rating == 4.7
    assert h1.review_count == 3200
    assert h1.nightly_price == 7500.0
    assert h1.total_price == 15000.0
    assert h1.free_cancellation is True
    assert h1.booking_url == "https://www.google.com/travel/hotels/taj"

    # Price comparison sources
    assert len(h1.price_sources) == 3
    cheapest_sources = [ps for ps in h1.price_sources if ps.is_cheapest]
    assert len(cheapest_sources) == 1
    assert cheapest_sources[0].source_name == "Booking.com"
    assert cheapest_sources[0].price == 7500.0

    h2 = hotels[1]
    assert h2.name == "City Heritage Inn"
    assert h2.star_class == 3
    assert h2.rating == 4.1
    assert h2.nightly_price == 2200.0
    assert h2.total_price == 4400.0


def test_parse_property_details():
    sources = hotel_service.parse_property_details(SAMPLE_PROPERTY_DETAILS, currency="INR")
    assert len(sources) == 3
    # Check that Agoda is marked as cheapest at 7250
    agoda = next(s for s in sources if s.source_name == "Agoda")
    assert agoda.is_cheapest is True
    assert agoda.price == 7250.0

    bcom = next(s for s in sources if s.source_name == "Booking.com")
    assert bcom.is_cheapest is False


def test_hotel_search_sends_filters_to_provider(monkeypatch):
    import asyncio
    from app.models.hotel import HotelSearchRequest
    from app.services import hotel_service as hs

    captured = {}

    async def fake_search(params):
        captured.update(params)
        return {"properties": []}

    monkeypatch.setattr(hs.serpapi_client, "search", fake_search)
    req = HotelSearchRequest(destination="Amritsar", check_in_date="2026-11-10",
                             check_out_date="2026-11-12", min_rating=4.0, star_class=4,
                             free_cancellation=True, max_price=6000)
    asyncio.run(hs.hotel_service.search_hotels(req))
    assert captured["rating"] == 8 and captured["hotel_class"] == "4"
    assert captured["free_cancellation"] == "true" and captured["max_price"] == 6000
