"""Slow AI calls must not freeze the server, every day ends with a way back to the hotel, and two hotels
that are practically neighbours never produce a 'changing hotel' step."""

import asyncio
import time
from types import SimpleNamespace

import pytest

from app.models.itinerary import FoodStop, ItineraryDay, ItineraryPlaceItem, ItineraryResponse, ItinerarySegment
from app.services.directions_service import enrich_itinerary


def _place(name, lat, lon):
    return ItineraryPlaceItem(name=name, category="x", latitude=lat, longitude=lon)


def _seg(tw, *places):
    return ItinerarySegment(time_window=tw, title="T", description="d", places=list(places))


def _food(name, lat, lon):
    return FoodStop(name=name, cuisine="c", recommendation="r", latitude=lat, longitude=lon)


def _day(n, evening_window="05:30 PM – 09:30 PM"):
    return ItineraryDay(
        day_number=n, theme="t", estimated_day_cost="0",
        morning=_seg("09:00 AM – 12:00 PM", _place(f"M{n}", 41.89, 12.49)), food_stop_lunch=_food(f"L{n}", 41.90, 12.50),
        afternoon=_seg("01:00 PM – 04:30 PM", _place(f"A{n}", 41.892, 12.485)), food_stop_dinner=_food(f"D{n}", 41.90, 12.48),
        evening=_seg(evening_window, _place(f"E{n}", 41.901, 12.483)))


def _itinerary(days):
    return ItineraryResponse(title="t", destination="Rome", duration_days=len(days), estimated_budget_total="0", currency="INR",
                             pace="moderate", trip_overview="o", days=days, sources=[], disclaimer="d", data_mode="mock")


HOTEL = {"name": "Hotel Hiberia Rome", "address": "Via X 1", "latitude": 41.905, "longitude": 12.496}


# ---------------------------------------------------------------- the server stays responsive during a slow AI call
@pytest.mark.asyncio
async def test_slow_ai_call_does_not_block_other_requests(monkeypatch):
    from app.models.itinerary import ItineraryRequest
    from app.services.ai_service import ai_service

    def slow(prompt, system_prompt=None):
        time.sleep(0.6)                      # what the real (synchronous) Gemini call does
        return "not json"

    monkeypatch.setattr(ai_service, "_generate_with_fallback", slow)
    ticks = 0

    async def heartbeat():                   # stands in for every other visitor's request
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    beat = asyncio.create_task(heartbeat())
    req = ItineraryRequest(destination="Rome", duration_days=1)
    with pytest.raises(RuntimeError):
        await ai_service._generate_live_itinerary(req, verified_places=[])
    beat.cancel()
    assert ticks >= 6, f"the event loop was blocked (only {ticks} ticks during a 0.6 s AI call)"


# ---------------------------------------------------------------- every day ends with a way back to the hotel
def test_each_day_ends_with_return_to_hotel_except_departure_day():
    days = [_day(1), _day(2), _day(3)]
    it = _itinerary(days)
    enrich_itinerary(it, SimpleNamespace(transportation="public", transport_modes=None, selected_hotel=None,
                                         selected_outbound_transport=None), None, {1: HOTEL, 2: HOTEL, 3: HOTEL})
    rt = it.days[0].return_to_hotel
    assert rt["hotel_name"] == "Hotel Hiberia Rome" and rt["from_name"] == "E1"
    assert rt["directions"]["maps_url"].startswith("https://www.google.com/maps/dir/") and rt["directions"]["distance_km"] > 0
    assert rt["leave_at"] == "21:30" and rt["arrive_at"] > rt["leave_at"]          # last stop ends 09:30 PM
    assert it.days[1].return_to_hotel is not None
    assert it.days[2].return_to_hotel is None                                       # departure day: check-out, no night stay


def test_skipped_meal_is_left_out_of_the_walking_chain():
    day = _day(1)
    day.food_stop_lunch.skipped = True
    it = _itinerary([day, _day(2)])
    enrich_itinerary(it, SimpleNamespace(transportation="public", transport_modes=None, selected_hotel=None,
                                         selected_outbound_transport=None), None, {1: HOTEL, 2: HOTEL})
    assert it.days[0].food_stop_lunch.directions is None
    assert it.days[0].afternoon.places[0].directions["from_name"] == "M1"           # comes straight after the morning stop


# ---------------------------------------------------------------- hotels next to each other are not a "change"
@pytest.mark.asyncio
async def test_no_hotel_change_card_for_hotels_under_three_km_apart():
    from app.routes.itinerary import _build_day_notes
    near = {"name": "Hotel Near", "latitude": 41.9055, "longitude": 12.4965}        # < 1 km from HOTEL
    far = {"name": "Hotel Far", "latitude": 41.40, "longitude": 12.90}              # ~60 km away
    for second, expected in ((near, 0), (far, 1)):
        it = _itinerary([_day(1), _day(2), _day(3), _day(4)])
        it.stay_blocks = [
            {"index": 0, "area": "Rome", "start_day": 1, "end_day": 2, "needs_hotel": True, "hotel": HOTEL},
            {"index": 1, "area": "Rome", "start_day": 3, "end_day": 4, "needs_hotel": True, "hotel": second},
        ]
        await _build_day_notes(it, {1: HOTEL, 2: HOTEL, 3: second, 4: second}, {})
        assert sum(1 for n in it.days[2].notes if n["type"] == "hotel_change") == expected
