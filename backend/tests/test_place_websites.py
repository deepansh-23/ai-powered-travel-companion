"""Websites for itinerary places and restaurants come only from real place data, never from the AI."""

from types import SimpleNamespace

from app.models.itinerary import FoodStop, ItineraryDay, ItineraryPlaceItem, ItineraryResponse, ItinerarySegment
from app.services.ai_service import ai_service
from app.services.directions_service import enrich_itinerary


def _seg(*places):
    return ItinerarySegment(time_window="09:00 AM – 12:00 PM", title="T", description="d", places=list(places))


def _day(place, lunch, dinner):
    return ItineraryDay(day_number=1, theme="t", estimated_day_cost="0", morning=_seg(place), food_stop_lunch=lunch,
                        afternoon=_seg(), food_stop_dinner=dinner, evening=_seg())


def _response(day):
    return ItineraryResponse(title="t", destination="Rome", duration_days=1, estimated_budget_total="0", currency="INR", pace="x",
                             trip_overview="o", days=[day], sources=[], disclaimer="d", data_mode="mock")


REQ = SimpleNamespace(transportation="public", transport_modes=None, selected_hotel=None, selected_outbound_transport=None)
VERIFIED = [
    {"name": "Colosseum", "latitude": 41.89, "longitude": 12.49, "website": "https://colosseo-tickets.test/visit", "address": "Piazza"},
    {"name": "Trattoria Roma", "latitude": 41.90, "longitude": 12.50, "website": "www.trattoria-roma.test", "address": "Via 1"},
    {"name": "No Site Cafe", "latitude": 41.91, "longitude": 12.51, "website": None},
    {"name": "Bad Site Bar", "latitude": 41.92, "longitude": 12.52, "website": "javascript:alert(1)"},
]


def test_matching_places_and_restaurants_get_their_real_website():
    day = _day(ItineraryPlaceItem(name="Colosseum", category="History"),
               FoodStop(name="Trattoria Roma", cuisine="Italian", recommendation="r"),
               FoodStop(name="No Site Cafe", cuisine="Cafe", recommendation="r"))
    r = _response(day)
    enrich_itinerary(r, REQ, VERIFIED)
    assert r.days[0].morning.places[0].website == "https://colosseo-tickets.test/visit"
    assert r.days[0].food_stop_lunch.website == "https://www.trattoria-roma.test"      # bare www is turned into https
    assert r.days[0].food_stop_dinner.website is None                                   # no website in the data: no link


def test_unsafe_or_missing_websites_never_become_links():
    day = _day(ItineraryPlaceItem(name="Bad Site Bar", category="Bar"),
               FoodStop(name="Unknown Place", cuisine="x", recommendation="r"), FoodStop(name="Unknown 2", cuisine="x", recommendation="r"))
    r = _response(day)
    enrich_itinerary(r, REQ, VERIFIED)
    assert r.days[0].morning.places[0].website is None and r.days[0].food_stop_lunch.website is None


def test_websites_written_by_the_ai_are_dropped():
    d = {"morning": {"time_window": "9", "title": "t", "description": "d",
                     "places": [{"name": "Colosseum", "category": "x", "website": "https://invented.example.net"}]},
         "food_stop_lunch": {"name": "L", "cuisine": "c", "recommendation": "r", "website": "https://invented-restaurant.test"}}
    day = ai_service._build_day(d, 1, [], 1000)
    assert day.morning.places[0].website is None and day.food_stop_lunch.website is None


def test_a_later_pass_without_place_data_keeps_the_links_already_found():
    day = _day(ItineraryPlaceItem(name="Colosseum", category="History"),
               FoodStop(name="Trattoria Roma", cuisine="Italian", recommendation="r"), FoodStop(name="X", cuisine="c", recommendation="r"))
    r = _response(day)
    enrich_itinerary(r, REQ, VERIFIED)
    enrich_itinerary(r, REQ, None)                                                      # e.g. the finalize step
    assert r.days[0].morning.places[0].website == "https://colosseo-tickets.test/visit"
    assert r.days[0].food_stop_lunch.website == "https://www.trattoria-roma.test"
