"""Batch D: choosing how to travel between stays (flight / train / cab / other), and what it does to the notes and budget."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.itinerary import TransferChoice
from app.utils.budget import build_budget
from app.utils.day_timing import transfer_card
from app.utils.trip_planner import LONG_TRANSFER_KM, transfer_needs_choice

client = TestClient(app)

BASE = {"destination": "Karnataka", "source": "Delhi", "departure_date": "2099-03-10", "return_date": "2099-03-13",
        "duration_days": 4, "budget_per_person_per_day": 3000, "travelers_count": 2, "areas": ["Goa", "Gokarna"]}

FLIGHT = {"mode": "flight", "operator": "IndiGo", "number": "6E 77", "origin": "GOI (Dabolim Airport)",
          "destination": "GOK (Gokarna Airfield)", "departure_time": "2099-03-12 09:00",
          "arrival_time": "2099-03-12 10:10", "duration_formatted": "1h 10m", "price": 3500}
TRAIN = {"mode": "train", "operator": "Indian Railways (Konkan Kanya)", "number": "10111", "origin": "MAO Station",
         "destination": "GOK Station", "departure_time": "2099-03-12 08:00", "arrival_time": "2099-03-12 12:30",
         "duration_formatted": "4h 30m"}


_POINTS = {"Goa": (15.50, 73.83), "Gokarna": (14.55, 74.32)}


def _meta(response):
    """The sample (mock) plan has no coordinates, so give each area one: transfers can then be worked out."""
    return [{"day_number": d.day_number, "area": d.area, "points": [_POINTS[d.area]], "places": ["P"]} for d in response.days]


def _plan(**extra):
    with patch("app.routes.itinerary._day_meta", _meta):
        r = client.post("/api/itinerary/generate", json={**BASE, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _finalize(plan, choices):
    return client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": [], "travelers_count": 2,
                                                        "transfer_choices": choices})


# ------------------------------------------------------------------ when the traveller is asked
def test_long_moves_and_country_trips_ask_how_to_travel():
    assert LONG_TRANSFER_KM == 200
    assert transfer_needs_choice("country", 20) and transfer_needs_choice("state", 200) and transfer_needs_choice(None, 519)
    assert not transfer_needs_choice("city", 120) and not transfer_needs_choice("state", 199)


def test_generate_marks_each_transfer_with_its_date_and_whether_a_choice_is_needed():
    country = _plan(scope_kind="country", arrival_city="Goa")["transfers"]
    assert country and country[0]["needs_choice"] is True and country[0]["date"] and country[0]["to_stay"] == 1
    near = _plan()["transfers"]  # Goa -> Gokarna is well under 200 km and this is not a country trip
    assert near and near[0]["needs_choice"] is False


# ------------------------------------------------------------------ what a choice does
def test_a_chosen_flight_is_priced_live_and_replaces_the_cab_estimate():
    plan = _plan(scope_kind="country", arrival_city="Goa")
    r = _finalize(plan, [{"to_stay": 1, "mode": "flight", "option": FLIGHT}])
    assert r.status_code == 200, r.text
    data = r.json()
    lines = {l["key"]: l for l in data["cost_breakdown"]["detail"]["lines"]}
    flight = [l for k, l in lines.items() if k.startswith("transfer_")][0]
    assert flight["kind"] == "live" and flight["total"] == 3500 * 2 and "flight" in flight["label"]
    assert "transfers" not in lines  # no cab estimate for a leg that is flown
    assert data["transfers"][0]["choice"]["mode"] == "flight" and data["transfers"][0]["choice"]["price"] == 3500


def test_flight_choice_adds_a_travel_card_with_real_times_on_the_moving_day():
    plan = _plan(scope_kind="country", arrival_city="Goa")
    days = {d["day_number"]: d for d in _finalize(plan, [{"to_stay": 1, "mode": "flight", "option": FLIGHT}]).json()["days"]}
    move_day = plan["stay_blocks"][1]["start_day"]
    cards = days[move_day]["notes"]
    assert [n["type"] for n in cards if n["type"] in ("transfer", "hotel_change")] == ["transfer"]
    text = " ".join(next(n for n in cards if n["type"] == "transfer")["lines"])
    assert "leaves 09:00, arrives 10:10" in text and "2 hours before departure" in text and "Check-in is usually from 14:00" in text


def test_train_has_no_invented_fare_and_cab_keeps_the_estimate():
    plan = _plan(scope_kind="country", arrival_city="Goa")
    train = _finalize(plan, [{"to_stay": 1, "mode": "train", "option": TRAIN}]).json()["cost_breakdown"]["detail"]
    assert any("by train" in m and "not in the total" in m for m in train["missing"])
    assert not any(l["key"].startswith("transfer_") for l in train["lines"])
    cab = _finalize(plan, [{"to_stay": 1, "mode": "cab"}]).json()["cost_breakdown"]["detail"]
    assert any(l["key"] == "transfers" and "cab" in l["label"] for l in cab["lines"])
    other = _finalize(plan, [{"to_stay": 1, "mode": "other"}]).json()["cost_breakdown"]["detail"]
    assert any("by other" in m for m in other["missing"])


def test_no_choice_still_works_with_the_old_cab_estimate():
    detail = _finalize(_plan(scope_kind="country", arrival_city="Goa"), []).json()["cost_breakdown"]["detail"]
    assert any(l["key"] == "transfers" for l in detail["lines"])


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        TransferChoice(to_stay=1, mode="rocket")
    assert TransferChoice(to_stay=1, mode="flight", option={"price": 1}).option == {"price": 1}


def test_budget_mixes_flight_train_and_cab_correctly():
    detail = build_budget(travelers=2, days=6, per_day_per_person=3000, rooms=1, hotels=[], transfers=[
        {"label": "A → B", "mode": "flight", "live_price_pp": 4200, "distance_km": 500, "cost_per_person": 1700},
        {"label": "B → C", "mode": "train", "distance_km": 300, "cost_per_person": 1000},
        {"label": "C → D", "mode": "cab", "distance_km": 100, "cost_per_person": 350}])
    assert [l["total"] for l in detail["lines"] if l["key"].startswith("transfer_")] == [8400]
    assert [l["total"] for l in detail["lines"] if l["key"] == "transfers"] == [700]
    assert len(detail["missing"]) == 1


def test_transfer_card_for_a_train():
    card = transfer_card(TRAIN, "Goa", "Gokarna", {"name": "Hotel A"}, {"name": "Hotel B"})
    text = " ".join(card["lines"])
    assert card["type"] == "transfer" and card["mode"] == "train" and "be at the station by 07:00 (1 hour before departure)" in text
    assert "Konkan Kanya 10111" in text and "Hotel B" in text


# ------------------------------------------------------------------ airport / station position for hotel ranking
def test_terminal_location_returns_coordinates_or_not_found():
    class C:  # stands in for the geocoder's centre
        latitude, longitude = 15.38, 73.83

    with patch("app.routes.transport.settings") as s, patch("app.routes.transport.geocoding_service.resolve_center", return_value=C()):
        s.MOCK_MODE = False
        r = client.post("/api/transport/terminal-location", json={"name": "Dabolim Airport"})
        assert r.json() == {"found": True, "latitude": 15.38, "longitude": 73.83, "name": "Dabolim Airport"}
    with patch("app.routes.transport.settings") as s, \
         patch("app.routes.transport.geocoding_service.resolve_center", side_effect=ValueError("nope")):
        s.MOCK_MODE = False
        assert client.post("/api/transport/terminal-location", json={"name": "Nowhere Airstrip"}).json() == {"found": False}
    assert client.post("/api/transport/terminal-location", json={"name": "x"}).status_code == 422


# ------------------------------------------------------------------ "Plan your area": always offers places and a start city
import asyncio

from app.services import scope_service as ss
from app.utils.scope_defaults import COUNTRIES, STATES, static_scope


def test_built_in_list_gives_a_start_city_and_places_for_popular_countries_and_states():
    italy = static_scope("country", "Italy")
    assert italy["gateway"] == "Rome" and [p["name"] for p in italy["inside"]][:3] == ["Florence", "Venice", "Milan"]
    assert static_scope("state", "Kerala")["gateway"] == "Kochi" and "Tamil Nadu" in [n["name"] for n in static_scope("state", "Kerala")["neighbours"]]
    assert static_scope("country", "Italy, Europe")["gateway"] == "Rome"
    assert static_scope("city", "Rome") is None and static_scope("country", "Narnia") is None
    for table in (COUNTRIES, STATES):
        for name, v in table.items():
            assert v["gateway"], name
            assert v["gateway"].lower() not in {p["name"].lower() for p in v["inside"]}, name


def test_scope_response_suggests_a_start_city_first_then_the_other_places():
    s = ss.build_scope("country", "Italy", 10, static_scope("country", "Italy"), "static")
    assert s.default_arrival == "Rome" and s.default_arrival_note == "capital" and s.needs_arrival and s.source == "static"
    assert [o["name"] for o in s.arrival_options][:3] == ["Rome", "Florence", "Venice"] and len(s.arrival_options) <= 6
    assert [x["name"] for x in s.suggestions][0] == "Florence"
    city = ss.build_scope("city", "Jaipur", 4, {"nearby": [{"name": "Agra"}]})
    assert city.default_arrival is None and city.arrival_options == [] and not city.needs_arrival


def test_when_the_ai_fails_the_built_in_list_is_used_instead_of_an_empty_panel():
    async def run(ai):
        with patch.object(ss.scope_service, "detect_kind", new=AsyncMock(return_value="country")), \
             patch.object(ss.scope_service, "_ask_ai", new=AsyncMock(return_value=ai)):
            return await ss.scope_service.scope("Italy", 10)

    none = asyncio.run(run(None))
    assert none.source == "static" and none.default_arrival == "Rome" and none.suggestions
    partial = asyncio.run(run({"gateway": "Milan"}))   # the AI gave a start city but no places: fill the gaps
    assert partial.default_arrival == "Milan" and partial.suggestions and partial.source == "ai"
    assert partial.default_arrival_note == "", "the built-in 'capital' note belongs to Rome, not Milan"
    full = asyncio.run(run({"gateway": "Rome", "inside": [{"name": "Turin", "note": "x"}]}))
    assert [x["name"] for x in full.suggestions] == ["Turin"] and full.source == "ai"


def test_unlisted_place_without_ai_still_asks_for_a_start_city():
    async def run():
        with patch.object(ss.scope_service, "_ask_ai", new=AsyncMock(return_value=None)):
            return await ss.scope_service.scope("Narnia", 6, "country")

    s = asyncio.run(run())
    assert s.source == "basic" and s.needs_arrival and s.default_arrival is None and s.suggestions == []


def test_ai_reply_with_extra_words_around_the_json_is_still_read():
    assert ss.parse_scope_json('Sure! Here you go:\n{"gateway": "Rome", "inside": []}\nEnjoy.') == {"gateway": "Rome", "inside": []}
    with pytest.raises(ValueError):
        ss.parse_scope_json("no json at all")
