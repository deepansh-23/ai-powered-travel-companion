"""Phase 2: city/state/country scope, days split between places, one hotel per stay, finalize."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.itinerary import ItineraryResponse
from app.services import scope_service as ss
from app.services.scope_service import build_scope, parse_scope_json
from app.utils.trip_planner import allocate_days, block_transfers, plan_stay_blocks

client = TestClient(app)


# ------------------------------------------------------------------ pure planner helpers
def test_days_are_shared_between_places_and_every_place_gets_a_day():
    s = allocate_days(["Jaipur", "Agra", "Delhi"], 7)
    assert len(s) == 7 and set(s) == {"Jaipur", "Agra", "Delhi"}
    assert s == sorted(s, key=["Jaipur", "Agra", "Delhi"].index)  # one visit per place, in order
    assert allocate_days(["A", "B", "C"], 2) == ["A", "B"]


def test_stay_blocks_split_by_area_nights_and_distance():
    days = [{"day_number": i + 1, "area": a, "points": [pt], "places": [f"P{i + 1}"]} for i, (a, pt) in enumerate(
        [("Jaipur", (26.9, 75.8))] * 3 + [("Agra", (27.17, 78.04))] * 2 + [("Delhi", (28.61, 77.2))] * 2)]
    blocks = plan_stay_blocks(days, "2099-03-10")
    assert [b["nights"] for b in blocks] == [3, 2, 1] and sum(b["nights"] for b in blocks) == 6
    assert blocks[0]["check_in"] == "2099-03-10" and blocks[1]["check_in"] == blocks[0]["check_out"]
    assert block_transfers(blocks)[0]["distance_km"] > 150

    long_stay = [{"day_number": i, "area": "Rome", "points": [(41.9, 12.5)]} for i in range(1, 6)]
    assert [b["nights"] for b in plan_stay_blocks(long_stay)] == [3, 1]
    assert plan_stay_blocks([{"day_number": 1, "area": "Goa"}])[0]["needs_hotel"] is False


# ------------------------------------------------------------------ scope questions
def test_city_gets_nearby_option_state_gets_neighbours_country_gets_regions():
    ai = {"nearby": [{"name": "Agra", "note": "Taj Mahal"}], "inside": [{"name": "Kochi"}, {"name": "Kerala"}],
          "neighbours": [{"name": "Tamil Nadu"}]}
    city = build_scope("city", "Jaipur", 5, ai)
    assert [m["value"] for m in city.modes] == ["only", "nearby"] and city.suggestions[0]["name"] == "Agra" and not city.needs_arrival
    state = build_scope("state", "Kerala", 6, ai)
    assert state.needs_arrival and [m["value"] for m in state.modes] == ["inside", "neighbours"]
    assert [x["name"] for x in state.suggestions] == ["Kochi"]  # the state itself is never suggested
    assert state.neighbours[0]["name"] == "Tamil Nadu"
    country = build_scope("country", "Italy", 10, {"inside": [{"name": "Rome"}]})
    assert country.needs_arrival and country.modes == [] and country.recommended_areas == 3


def test_scope_works_without_ai():
    s = build_scope("country", "Italy", 7, None)
    assert s.source == "basic" and s.suggestions == [] and s.needs_arrival


def test_ai_reply_with_code_fences_is_parsed():
    assert parse_scope_json('```json\n{"inside": []}\n```') == {"inside": []}


def test_scope_endpoint_uses_the_service():
    resp = build_scope("city", "Jaipur", 3, None)
    with patch.object(ss.scope_service, "scope", new=AsyncMock(return_value=resp)):
        r = client.post("/api/itinerary/scope", json={"destination": "Jaipur", "duration_days": 3})
    assert r.status_code == 200 and r.json()["kind"] == "city" and r.json()["modes"][0]["value"] == "only"


# ------------------------------------------------------------------ generate (mock mode) -> finalize
BASE = {"destination": "Goa", "source": "Delhi", "departure_date": "2099-03-10", "return_date": "2099-03-13",
        "duration_days": 4, "budget_per_person_per_day": 3000, "travelers_count": 2, "interests": ["Culture"]}


def test_generate_returns_stay_blocks_and_no_hotel():
    r = client.post("/api/itinerary/generate", json=BASE)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["selected_hotel"] is None
    assert data["stay_blocks"] and all(d["area"] for d in data["days"])
    assert sum(b["nights"] for b in data["stay_blocks"]) == data["duration_days"] - 1


def test_several_areas_share_the_days():
    r = client.post("/api/itinerary/generate", json={**BASE, "duration_days": 6, "areas": ["Goa", "Gokarna", "Hampi"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [b["area"] for b in data["stay_blocks"]] == ["Goa", "Gokarna", "Hampi"]
    assert {d["area"] for d in data["days"]} == {"Goa", "Gokarna", "Hampi"}


def test_finalize_adds_each_hotel_and_a_multi_hotel_budget():
    plan = client.post("/api/itinerary/generate", json={**BASE, "duration_days": 6, "areas": ["Goa", "Gokarna", "Hampi"]}).json()
    plan["selected_outbound_transport"] = {"price": 4000}
    plan["selected_return_transport"] = {"price": 3500}
    needing = [b for b in plan["stay_blocks"] if b["needs_hotel"]]
    stays = [{"block_index": b["index"], "hotel": {"name": f"Hotel {b['area']}", "total_price": 6000, "nightly_price": 2000}}
             for b in needing[:2]] + [{"block_index": needing[2]["index"], "hotel": None}]
    r = client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": stays, "travelers_count": 2,
                                                     "budget_per_person_per_day": 3000})
    assert r.status_code == 200, r.text
    data = r.json()
    assert [h["name"] for h in data["selected_hotels"]] == ["Hotel Goa", "Hotel Gokarna"]
    assert data["selected_hotel"]["name"] == "Hotel Goa"
    detail = data["cost_breakdown"]["detail"]
    assert sum(l["total"] for l in detail["lines"] if l["key"].startswith("stay_")) == 6000 * 2 * 1 * 2  # 2 hotels x 1 room
    assert detail["rooms"] == 1 and not any("Hampi" in m for m in detail["missing"])  # skipped on purpose
    assert data["estimated_budget_total"].endswith("total estimate")
    assert data["stay_blocks"][0]["hotel"]["name"] == "Hotel Goa"


def test_finalize_without_any_hotel_says_what_is_missing():
    plan = client.post("/api/itinerary/generate", json=BASE).json()
    r = client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": [], "travelers_count": 2})
    assert r.status_code == 200
    assert r.json()["selected_hotels"] is None
    assert any("no hotel selected" in m for m in r.json()["cost_breakdown"]["detail"]["missing"])
