"""Phase 1 fixes: airports for any city, per-person flight quotes, place suggestions,
Indian-station lookup for trains, and the trip budget breakdown. No live API calls."""

import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.itinerary import ItineraryRequest
from app.services import flight_service as fs
from app.services.ai_service import ai_service
from app.services.place_suggest_service import parse_autocomplete
from app.services.rail_service import rail_service
from app.utils.budget import build_budget, default_rooms

client = TestClient(app)

MUNICH = {"suggestions": [
    {"type": "city", "name": "Munich, Germany", "airports": [{"id": "MUC"}, {"id": "FMM"}]},
    {"type": "region", "name": "Bavaria"},
    {"type": "city", "name": "Munich Township", "airports": [{"id": "XXX"}]},
]}


# ------------------------------------------------------------------ airports for any city
def test_airport_picker_accepts_only_exact_city_names():
    assert fs.pick_airports_from_autocomplete(MUNICH, "Munich") == (["MUC", "FMM"], ["Munich Township"])
    codes, alternatives = fs.pick_airports_from_autocomplete(MUNICH, "Munchen")
    assert codes == [] and "Munich, Germany" in alternatives


BERGEN = {"suggestions": [
    {"type": "city", "name": "Bergen, Norway", "airports": [{"id": "BGO"}]},
    {"type": "city", "name": "Bergen County, New Jersey", "airports": [{"id": "TEB"}]},
]}
MANCHESTERS = {"suggestions": [
    {"type": "city", "name": "Manchester, New Hampshire", "description": "United States", "airports": [{"id": "MHT"}]},
    {"type": "city", "name": "Manchester, England", "description": "United Kingdom", "airports": [{"id": "MAN"}]},
]}
NO_SUGGESTIONS = AsyncMock(return_value=([], None))


def test_unknown_city_is_resolved_live_then_cached():
    fs._airport_cache.clear()
    search = AsyncMock(return_value=BERGEN)
    with patch.object(fs.serpapi_client, "search", new=search):
        assert asyncio.run(fs.resolve_airports("Bergen")) == (["BGO"], None)
        assert asyncio.run(fs.resolve_airports("bergen, norway")) == (["BGO"], None)
    assert search.await_count == 1  # second lookup came from the cache


def test_plain_city_names_need_no_airport_code():
    # these used to fail until the IATA code (MAN, CPH, MUC) was typed
    with patch.object(fs.serpapi_client, "search", new=AsyncMock(side_effect=AssertionError("no call expected"))):
        for city, code in (("Manchester", "MAN"), ("Copenhagen", "CPH"), ("Munich", "MUC"), ("manchester, England, United Kingdom", "MAN")):
            assert asyncio.run(fs.resolve_airports(city)) == ([code], None), city


def test_same_city_name_is_disambiguated_by_the_words_after_the_comma():
    codes, _ = fs.pick_airports_from_autocomplete(MANCHESTERS, "Manchester, United Kingdom")
    assert codes == ["MAN"]
    codes, _ = fs.pick_airports_from_autocomplete(MANCHESTERS, "Manchester, New Hampshire")
    assert codes == ["MHT"]


def test_an_airport_listed_on_its_own_is_accepted():
    data = {"suggestions": [{"type": "airport", "name": "Bergen Flesland Airport", "id": "BGO"}]}
    assert fs.pick_airports_from_autocomplete(data, "Bergen")[0] == ["BGO"]


def test_misspelt_city_is_corrected_with_the_recognised_spelling():
    fs._airport_cache.clear()

    async def fake_search(params, timeout=25.0):
        q = params["q"].lower()
        return BERGEN if q.startswith("bergen") else {"suggestions": []}

    suggestion = [{"label": "Bergen, Vestland, Norway", "name": "Bergen", "kind": "city", "kind_label": "City",
                   "country": "Norway", "state": "Vestland"}]
    with patch.object(fs.serpapi_client, "search", new=fake_search), \
         patch("app.services.place_suggest_service.place_suggest_service.suggest", new=AsyncMock(return_value=(suggestion, None))):
        assert asyncio.run(fs.resolve_airports("Bergn")) == (["BGO"], None)


def test_known_cities_do_not_use_the_api():
    with patch.object(fs.serpapi_client, "search", new=AsyncMock(side_effect=AssertionError("no call expected"))):
        assert asyncio.run(fs.resolve_airports("Delhi")) == (["DEL"], None)
        codes, notice = asyncio.run(fs.resolve_airports("Rishikesh"))
    assert codes == [] and "No commercial airport" in notice


def test_unresolvable_city_gives_did_you_mean_notice():
    fs._airport_cache.clear()
    with patch.object(fs.serpapi_client, "search", new=AsyncMock(return_value=BERGEN)), \
         patch("app.services.place_suggest_service.place_suggest_service.suggest", new=NO_SUGGESTIONS):
        codes, notice = asyncio.run(fs.resolve_airports("Bergn"))
    assert codes == [] and "Did you mean" in notice and "Bergen, Norway" in notice


def test_airport_lookup_failure_falls_back_to_the_old_notice():
    fs._airport_cache.clear()
    with patch.object(fs.serpapi_client, "search", new=AsyncMock(side_effect=RuntimeError("no key"))):
        codes, notice = asyncio.run(fs.resolve_airports("Bergen"))
    assert codes == [] and "Could not verify a commercial airport" in notice


def test_flights_are_always_quoted_for_one_adult():
    seen = []

    async def fake_search(params, timeout=25.0):
        seen.append(params["adults"])
        return {"best_flights": [], "other_flights": []}

    with patch.object(fs.serpapi_client, "search", new=fake_search):
        asyncio.run(fs.flight_service.search_flights("Delhi", "Mumbai", "2099-01-01", adults=1))
    assert seen and set(seen) == {1}


# ------------------------------------------------------------------ trains outside India
def test_trains_outside_india_are_skipped_with_a_clear_notice():
    with patch.object(rail_service, "find_stations", new=AsyncMock(return_value=([], "none"))):
        options, notice = asyncio.run(rail_service.search_trains("Munich", "Copenhagen", "2099-01-01"))
    assert options == [] and "India only" in notice


def test_indian_city_missing_from_the_builtin_list_uses_railradar_stations():
    stations = [{"code": "NK", "name": "Nasik Road", "city": "Nashik"}]
    with patch.object(rail_service, "find_stations", new=AsyncMock(return_value=(stations, None))):
        assert asyncio.run(rail_service.resolve_station_code_live("Nashik, Maharashtra")) == "NK"
    assert rail_service.resolve_station_code("Delhi, India") == rail_service.resolve_station_code("Delhi")


# ------------------------------------------------------------------ place suggestions
def test_place_suggestions_are_parsed_and_deduplicated():
    data = {"results": [
        {"result_type": "city", "city": "Munich", "state": "Bavaria", "country": "Germany"},
        {"result_type": "city", "city": "Munich", "state": "Bavaria", "country": "Germany"},
        {"result_type": "state", "state": "New York", "country": "United States"},
        {"result_type": "city", "city": "New York", "state": "New York", "country": "United States"},
        {"result_type": "country", "country": "Denmark"},
        {"result_type": "street", "name": "Munich Street"},
    ]}
    out = parse_autocomplete(data)
    assert [(o["kind"], o["label"]) for o in out] == [
        ("city", "Munich, Bavaria, Germany"), ("state", "New York, United States"),
        ("city", "New York, United States"), ("country", "Denmark")]


def test_suggest_endpoint():
    items = [{"label": "Munich, Bavaria, Germany", "name": "Munich", "kind": "city", "kind_label": "City"}]
    with patch("app.routes.places.place_suggest_service.suggest", new=AsyncMock(return_value=(items, None))):
        r = client.get("/api/places/suggest", params={"q": "mun"})
    assert r.status_code == 200 and r.json()["suggestions"][0]["name"] == "Munich"


# ------------------------------------------------------------------ budget
def test_budget_multiplies_per_person_prices_and_separates_live_from_estimates():
    b = build_budget(travelers=3, days=4, per_day_per_person=3000, outbound_pp=5000, return_pp=4000, hotel_total_per_room=9000)
    assert default_rooms(3) == 2 and b["rooms"] == 2 and b["nights"] == 3
    assert b["live_total"] == 5000 * 3 + 4000 * 3 + 9000 * 2
    assert b["grand_total"] == b["live_total"] + b["estimate_total"]
    assert {l["kind"] for l in b["lines"]} == {"live", "estimate"}
    assert b["per_person_total"] == round(b["grand_total"] / 3)


def test_budget_says_what_is_missing_instead_of_guessing():
    b = build_budget(travelers=1, days=2, per_day_per_person=2000)
    assert len(b["missing"]) == 3 and b["live_total"] == 0


def test_itinerary_cost_breakdown_keeps_old_keys_and_adds_detail():
    req = ItineraryRequest(destination="Goa", duration_days=3, travelers_count=2, budget_per_person_per_day=2000,
                           selected_outbound_transport={"price": 4000}, selected_return_transport={"price": 3500},
                           selected_hotel={"total_price": 6000})
    cb = ai_service._calculate_cost_breakdown(req, 0)
    assert cb["detail"]["live_total"] == 4000 * 2 + 3500 * 2 + 6000 * 1
    assert cb["overall_total_estimate"] == cb["detail"]["grand_total"]
    assert cb["hotel_selected"] and cb["transport_selected"]
