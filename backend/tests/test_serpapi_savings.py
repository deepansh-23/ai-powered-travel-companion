"""SerpApi savings: one search per flight leg (best airport pair only) and nearby dates only on request.

Every test replaces serpapi_client.search with a counting fake: no network, no SerpApi credits.
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.models.transport import TransportSearchRequest
from app.services import flight_service as fs
from app.services.rail_service import rail_service
from app.services.transport_search_service import transport_search_service

DAY = (date.today() + timedelta(days=40)).isoformat()
BACK = (date.today() + timedelta(days=45)).isoformat()


def _payload(dep: str, arr: str, price: int, when: str):
    return {"best_flights": [{
        "flights": [{
            "departure_airport": {"name": dep, "id": dep, "time": f"{when} 06:15"},
            "arrival_airport": {"name": arr, "id": arr, "time": f"{when} 08:25"},
            "duration": 130, "airline": "TestAir", "flight_number": "TA 101", "travel_class": "Economy",
        }],
        "total_duration": 130, "price": price, "type": "One way", "booking_token": "tok",
    }], "other_flights": []}


class FakeSerp:
    """Counts calls and answers from a script. Behaviour: results | empty | error."""

    def __init__(self, behaviour="results"):
        self.calls, self.behaviour = [], behaviour

    async def __call__(self, params, timeout=25.0):
        self.calls.append(dict(params))
        if self.behaviour == "error":
            raise RuntimeError("SerpApi search quota exceeded or rate limit reached.")
        if self.behaviour == "empty":
            return {"best_flights": [], "other_flights": []}
        return _payload(params["departure_id"], params["arrival_id"], 5000, params["outbound_date"])

    def flights(self):
        return [c for c in self.calls if c.get("engine") == "google_flights"]


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ one-way
def test_one_way_makes_one_search_with_the_best_airport_pair():
    fake = FakeSerp()
    with patch.object(fs.serpapi_client, "search", new=fake):
        options, notice = _run(fs.flight_service.search_flights("London", "New York", DAY))   # 2 airports each
    assert len(fake.calls) == 1                                           # was up to 4 (every airport pair)
    c = fake.calls[0]
    assert (c["departure_id"], c["arrival_id"], c["outbound_date"], c["type"]) == ("LHR", "JFK", DAY, "2")
    assert notice is None and len(options) == 1 and options[0].price == 5000
    assert options[0].raw_provider_data["search_params"]["departure_id"] == "LHR"   # booking flow keeps its parameters


def test_airport_choice_comes_from_the_existing_selection_not_a_hardcoded_pair():
    fake = FakeSerp()
    with patch.object(fs.serpapi_client, "search", new=fake):
        _run(fs.flight_service.search_flights("Delhi", "Mumbai", DAY))
        _run(fs.flight_service.search_flights("Paris", "London", DAY))
    assert [(c["departure_id"], c["arrival_id"]) for c in fake.calls] == [("DEL", "BOM"), ("CDG", "LHR")]


def test_same_first_airport_falls_back_to_a_distinct_pair_with_still_one_search():
    fake = FakeSerp()
    with patch.object(fs.serpapi_client, "search", new=fake), \
         patch.object(fs, "resolve_airports", new=AsyncMock(side_effect=[(["LHR", "LGW"], None), (["LHR"], None)])):
        _run(fs.flight_service.search_flights("A", "B", DAY))
    assert len(fake.calls) == 1 and (fake.calls[0]["departure_id"], fake.calls[0]["arrival_id"]) == ("LGW", "LHR")


# ------------------------------------------------------------------ return trip
def _search_transport(fake, **extra):
    req = TransportSearchRequest(source="Delhi", destination="Mumbai", outbound_date=DAY, return_date=BACK, travelers=2, **extra)
    with patch.object(fs.serpapi_client, "search", new=fake), \
         patch.object(rail_service, "search_trains", new=AsyncMock(return_value=([], None))):
        return _run(transport_search_service.search_transport(req))


def test_return_trip_is_exactly_one_outbound_and_one_return_search():
    fake = FakeSerp()
    res = _search_transport(fake)
    assert len(fake.flights()) == 2
    out, back = fake.flights()
    assert (out["departure_id"], out["arrival_id"], out["outbound_date"], out["adults"]) == ("DEL", "BOM", DAY, 1)
    assert (back["departure_id"], back["arrival_id"], back["outbound_date"], back["adults"]) == ("BOM", "DEL", BACK, 1)
    assert len(res.outbound.flights) == 1 and len(res.return_leg.flights) == 1      # response format unchanged
    assert res.outbound.flights[0].price == 5000


def test_one_way_trip_through_the_full_search_is_one_flight_search():
    fake = FakeSerp()
    req = TransportSearchRequest(source="Delhi", destination="Mumbai", outbound_date=DAY, travelers=1)
    with patch.object(fs.serpapi_client, "search", new=fake), \
         patch.object(rail_service, "search_trains", new=AsyncMock(return_value=([], None))):
        res = _run(transport_search_service.search_transport(req))
    assert len(fake.flights()) == 1 and res.return_leg is None


# ------------------------------------------------------------------ empty results and errors
def test_empty_results_do_not_trigger_an_alternative_airport_search():
    fake = FakeSerp("empty")
    res = _search_transport(fake)
    assert len(fake.flights()) == 2                                       # still only the two chosen legs
    assert res.outbound.flights == [] and res.return_leg.flights == []


def test_api_error_is_reported_without_retrying_other_pairs_or_dates():
    fake = FakeSerp("error")
    with patch.object(fs.serpapi_client, "search", new=fake):
        with pytest.raises(RuntimeError):
            _run(fs.flight_service.search_flights("London", "New York", DAY))
    assert len(fake.calls) == 1
    fake2 = FakeSerp("error")
    res = _search_transport(fake2)                                        # the page still loads: a notice, no crash
    assert len(fake2.flights()) == 2
    assert "Flights unavailable" in res.outbound.airport_notice and "Flights unavailable" in res.return_leg.airport_notice


def test_unresolvable_city_makes_no_flight_search():
    fake = FakeSerp()
    with patch.object(fs.serpapi_client, "search", new=fake):
        options, notice = _run(fs.flight_service.search_flights("Hampi", "Mumbai", DAY))
    assert options == [] and notice and not fake.flights()


# ------------------------------------------------------------------ nearby dates are on request only
def test_normal_search_never_asks_for_nearby_dates_but_the_on_request_call_still_works():
    fake = FakeSerp()
    _search_transport(fake)
    assert {c["outbound_date"] for c in fake.flights()} == {DAY, BACK}    # only the dates the traveller chose
    explicit = FakeSerp()
    with patch.object(fs.serpapi_client, "search", new=explicit):
        res = _run(transport_search_service.flight_date_prices("Delhi", "Mumbai", DAY, 1, "INR"))
    assert len(explicit.flights()) == 5 and len(res.days) == 5            # 5 dates x ONE airport pair (was up to 5 x 4)


def test_frontend_no_longer_fetches_nearby_dates_automatically():
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[2].joinpath("frontend/js/pages/itinerary.js").read_text()
    assert "else if (fetchStrip) this.loadDateStrip(legType);" not in src
    assert "else if (fetchStrip) this.showDateStripPrompt(legType);" in src
