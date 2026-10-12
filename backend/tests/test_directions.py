"""Stop-to-stop directions: origin is always the previous stop, never 'current location'."""

from urllib.parse import parse_qs, urlparse

from app.models.itinerary import (
    FoodStop, ItineraryDay, ItineraryPlaceItem, ItineraryRequest, ItineraryResponse, ItinerarySegment,
)
from app.services.directions_service import (
    compass_heading, enrich_itinerary, estimate_minutes, haversine_km, suggest_mode,
)

PLACES = [
    {"name": "Golden Temple", "address": "Amritsar", "latitude": 31.6200, "longitude": 74.8765},
    {"name": "Kesar Da Dhaba", "address": "Chowk Passian", "latitude": 31.6215, "longitude": 74.8790},
    {"name": "Jallianwala Bagh", "address": "Amritsar", "latitude": 31.6206, "longitude": 74.8800},
    {"name": "Wagah Border", "address": "Attari", "latitude": 31.6040, "longitude": 74.5730},
]


def _seg(*names):
    return ItinerarySegment(
        time_window="9-12", title="t", description="d",
        places=[ItineraryPlaceItem(name=n, category="sight", address="Amritsar") for n in names],
    )


def _food(name):
    return FoodStop(name=name, cuisine="Punjabi", recommendation="Kulcha")


def _day(n, morning, lunch, afternoon, dinner, evening):
    return ItineraryDay(
        day_number=n, theme="x", estimated_day_cost="1000",
        morning=_seg(*morning), food_stop_lunch=_food(lunch),
        afternoon=_seg(*afternoon), food_stop_dinner=_food(dinner), evening=_seg(*evening),
    )


def _response(days):
    return ItineraryResponse(
        title="t", destination="Amritsar", duration_days=len(days), estimated_budget_total="1",
        currency="INR", pace="moderate", trip_overview="o", days=days, sources=[], disclaimer="d",
        data_mode="live",
    )


def _req(**kw):
    return ItineraryRequest(destination="Amritsar", **kw)


def _origin(item):
    return parse_qs(urlparse(item.directions["maps_url"]).query)["origin"][0]


def test_math_helpers():
    assert 0.0 < haversine_km(31.62, 74.8765, 31.6215, 74.879) < 0.5
    assert compass_heading(31.0, 74.0, 32.0, 74.0) == "north"
    assert compass_heading(31.0, 74.0, 31.0, 75.0) == "east"
    assert suggest_mode(0.5, "public")[0] == "Walk"
    assert suggest_mode(2.5, "public")[1] == "driving"
    assert suggest_mode(8, "public")[1] == "transit"
    assert suggest_mode(5, "walking")[0] == "Walk"
    assert estimate_minutes(1.0, "Walk") > 10


def test_each_stop_starts_from_previous_stop_not_current_location():
    day = _day(1, ["Golden Temple"], "Kesar Da Dhaba", ["Jallianwala Bagh"], "Kesar Da Dhaba", [])
    resp = _response([day])
    hotel = {"name": "Hotel Ritz", "address": "Mall Road", "latitude": 31.63, "longitude": 74.87}
    enrich_itinerary(resp, _req(selected_hotel=hotel), PLACES)

    temple = day.morning.places[0]
    lunch = day.food_stop_lunch
    bagh = day.afternoon.places[0]

    assert temple.directions["from_name"] == "Hotel Ritz"           # first stop: from the hotel
    assert _origin(temple) == "31.63,74.87"
    assert lunch.directions["from_name"] == "Golden Temple"         # restaurant: from last visited place
    assert _origin(lunch) == "31.62,74.8765"
    assert bagh.directions["from_name"] == "Kesar Da Dhaba"
    assert "current" not in temple.directions["maps_url"].lower()
    assert lunch.latitude == 31.6215 and lunch.directions["mode"] and lunch.directions["minutes"]
    assert "head" in lunch.directions["summary"] and lunch.directions["distance_km"] is not None


def test_day_one_without_hotel_starts_at_arrival_point_then_day_two_continues_from_last_stop():
    d1 = _day(1, ["Golden Temple"], "Kesar Da Dhaba", [], "Kesar Da Dhaba", ["Jallianwala Bagh"])
    d2 = _day(2, ["Wagah Border"], "Kesar Da Dhaba", [], "Kesar Da Dhaba", [])
    resp = _response([d1, d2])
    enrich_itinerary(resp, _req(selected_outbound_transport={"destination": "Amritsar Junction"}), PLACES)

    assert d1.morning.places[0].directions["from_name"] == "Amritsar Junction"
    assert "Amritsar" in _origin(d1.morning.places[0])               # text origin: no coordinates for a station
    assert d2.morning.places[0].directions["from_name"] == "Jallianwala Bagh"  # last place of day 1
    assert d2.morning.places[0].directions["mode"].startswith("Local bus")     # ~25 km away


def test_unmatched_place_falls_back_to_text_links_without_crashing():
    day = _day(1, ["Some Unknown Museum"], "Mystery Cafe", [], "Mystery Cafe", [])
    resp = _response([day])
    enrich_itinerary(resp, _req(selected_hotel={"name": "Hotel Ritz", "address": "Mall Road"}), [])
    stop = day.morning.places[0]
    assert stop.latitude is None and stop.directions["distance_km"] is None
    assert "Hotel Ritz" in _origin(stop) and "open the map" in stop.directions["summary"]


def test_generate_endpoint_returns_directions_in_mock_mode():
    from fastapi.testclient import TestClient
    from app.main import app

    r = TestClient(app).post("/api/itinerary/generate", json={
        "destination": "Amritsar", "duration_days": 2,
        "selected_hotel": {"name": "Hotel Ritz", "address": "Mall Road"},
    })
    assert r.status_code == 200
    day = r.json()["days"][0]
    assert day["food_stop_lunch"]["directions"]["maps_url"].startswith("https://www.google.com/maps/dir/")
    assert day["morning"]["places"][0]["directions"]["from_name"] == "Hotel Ritz"
