"""Train class preferences, fare/availability honesty, AI train advice, station search,
and the nearby-dates flight price strip. No live API calls: everything is mocked."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.transport import (
    TrainClassInfo,
    TrainFareAvailability,
    TransportOption,
    TransportSearchRequest,
    normalize_train_classes,
)
from app.services import train_advisor_service as adv
from app.services import train_fare_service as fare
from app.services.rail_service import rail_service
from app.services.train_fare_service import normalize_availability
from app.services.transport_search_service import transport_search_service
from app.utils.price_tiers import build_date_note, classify_price_tiers

client = TestClient(app)


def _train(i, number, name, dur, stops=0, typ=""):
    return TransportOption(
        id=i, mode="train", provider="railradar", operator=f"Indian Railways ({name})", number=number,
        origin="NDLS Station", destination="BCT Station", departure_time="2026-11-04 16:55",
        arrival_time="2026-11-05 08:30", duration_minutes=dur, duration_formatted=f"{dur // 60}h {dur % 60}m",
        stops=stops, raw_provider_data={"train_type": typ},
    )


DIRECTORY = {
    "12952": {"classes": ["1A", "2A", "3A"]},
    "12904": {"classes": ["2A", "3A", "SL"]},
    "14033": {"classes": ["SL"]},
}


# ------------------------------------------------------------------ class selection
def test_train_classes_are_normalised():
    assert normalize_train_classes(["3AC", "sl", "3A", "1ac"]) == ["SL", "3A", "1A"]
    with pytest.raises(ValueError):
        normalize_train_classes(["CC"])
    req = TransportSearchRequest(source="Delhi", destination="Mumbai", outbound_date="2099-01-01",
                                 train_classes=["2AC"], source_station_code="ndls")
    assert req.train_classes == ["2A"] and req.source_station_code == "NDLS"


def test_bad_station_code_is_rejected_by_the_api():
    r = client.post("/api/transport/search", json={
        "source": "Delhi", "destination": "Mumbai", "outbound_date": "2099-01-01", "source_station_code": "N D!"})
    assert r.status_code == 422


# ------------------------------------------------------------------ availability + fares honesty
def test_availability_text_is_normalised():
    assert normalize_availability("AVAILABLE-0045") == "AVAILABLE"
    assert normalize_availability("RAC 12") == "RAC"
    assert normalize_availability("GNWL12/WL8") == "WL"
    assert normalize_availability("REGRET") is None and normalize_availability(None) is None


def test_no_classes_chosen_means_no_class_lookup():
    trains = [_train("a", "12952", "RAJDHANI", 975)]
    with patch.object(rail_service, "get_train_classes", new=AsyncMock(side_effect=AssertionError("must not be called"))):
        assert asyncio.run(fare.train_fare_service.enrich(trains, [], "NDLS", "BCT", "2026-11-04")) is None
    assert trains[0].fare_availability is None


def test_railradar_gives_verified_classes_but_never_invented_fares():
    trains = [_train("a", "12952", "RAJDHANI", 975), _train("c", "14033", "PASSENGER", 1900)]
    with patch.object(rail_service, "get_train_classes", new=AsyncMock(return_value=DIRECTORY)):
        notice = asyncio.run(fare.train_fare_service.enrich(trains, ["2A", "3A"], "NDLS", "BCT", "2026-11-04"))
    assert "not provided by RailRadar" in notice
    rows = trains[0].fare_availability.classes
    assert [r.code for r in rows] == ["2A", "3A"] and all(r.offered and r.data_quality == "verified" for r in rows)
    assert all(r.fare_per_person is None and r.availability_status is None for r in rows)
    assert trains[1].fare_availability.classes[0].offered is False


def test_unverifiable_classes_are_reported_as_unknown_not_guessed():
    trains = [_train("a", "12952", "RAJDHANI", 975)]
    with patch.object(rail_service, "get_train_classes", new=AsyncMock(side_effect=RuntimeError("RAILRADAR_API_KEY is not configured."))):
        notice = asyncio.run(fare.train_fare_service.enrich(trains, ["3A"], "NDLS", "BCT", "2026-11-04"))
    c = trains[0].fare_availability.classes[0]
    assert c.offered is None and c.data_quality == "unavailable" and "unavailable" in notice.lower()


def test_provider_is_asked_only_about_relevant_trains_and_classes():
    class Prov(fare.FareProvider):
        name, supports_fares, supports_availability = "fake", True, True

        def __init__(self):
            self.calls = []

        async def fetch(self, train, class_code, from_code, to_code, date_str):
            self.calls.append((train.number, class_code))
            return fare.ClassQuote(1500 if class_code == "3A" else None, "RAC 4" if class_code == "3A" else "???")

    prov = Prov()
    trains = [_train("a", "12952", "RAJDHANI", 975), _train("b", "12904", "MAIL", 1290)]
    with patch.object(rail_service, "get_train_classes", new=AsyncMock(return_value={
            "12952": {"classes": ["1A", "2A", "3A"]}, "12904": {"classes": ["SL"]}})):
        asyncio.run(fare.TrainFareService(prov).enrich(trains, ["3A"], "NDLS", "BCT", "2026-11-04"))
    assert prov.calls == [("12952", "3A")]
    q = trains[0].fare_availability.classes[0]
    assert (q.fare_per_person, q.availability_status) == (1500, "RAC")


# ------------------------------------------------------------------ AI / rule based advice
def test_advice_skips_trains_without_the_chosen_class_and_never_invents_cost():
    trains = [_train("t1", "12952", "MUMBAI RAJDHANI", 975, 0, "RAJ"),
              _train("t2", "12904", "GOLDEN TEMPLE MAIL", 1290, 5, "Superfast"),
              _train("t3", "14033", "PASSENGER SPL", 1900, 20, "Passenger")]
    with patch.object(rail_service, "get_train_classes", new=AsyncMock(return_value=DIRECTORY)):
        asyncio.run(fare.train_fare_service.enrich(trains, ["2A", "3A"], "NDLS", "BCT", "2026-11-04"))
    advice = asyncio.run(adv.train_advisor_service.advise(trains, ["2A", "3A"], "best-overall"))
    ids = [p.option_id for p in advice.picks]
    assert "t3" not in ids and advice.picks[0].option_id == "t1"
    assert not any("Cheapest" in p.label for p in advice.picks)
    assert any("cost could not be compared" in c for c in advice.caveats)
    assert "₹" not in advice.summary and advice.source == "rule-based"


def test_cheapest_pick_appears_only_with_real_fares():
    a, b = _train("x", "1", "A", 600), _train("y", "2", "B", 700)
    for t, f in ((a, 3000.0), (b, 1800.0)):
        t.fare_availability = TrainFareAvailability(classes=[TrainClassInfo(
            code="3A", label="3AC", offered=True, fare_per_person=f, availability_status="AVAILABLE", data_quality="verified")])
    advice = asyncio.run(adv.train_advisor_service.advise([a, b], ["3A"], "cheapest"))
    assert advice.picks[0].option_id == "y"
    assert any("Cheapest" in p.label for p in advice.picks)


def test_ai_text_with_made_up_money_is_rejected():
    facts = [adv.build_facts(_train("a", "12952", "RAJDHANI", 975))]
    assert not adv.ai_text_is_safe("The 3AC fare is about ₹2,500.", facts)
    assert not adv.ai_text_is_safe("", facts)
    assert adv.ai_text_is_safe("Take the Rajdhani: it is quickest.", facts)


# ------------------------------------------------------------------ stations
def test_station_results_are_cleaned_and_city_first():
    data = {"data": [
        {"code": "NZM", "name": "Hazrat Nizamuddin", "city": "Delhi"},
        {"code": "DELP", "name": "Delhi Cantt Spur", "city": "Other"},
        {"code": "ndls", "name": "New Delhi", "city": "Delhi"},
        {"code": "NDLS", "name": "dup", "city": "Delhi"},
        {"name": "no code"},
    ]}
    out = rail_service.parse_station_results(data, "delhi")
    assert [s["code"] for s in out] == ["NZM", "NDLS", "DELP"]


def test_station_endpoint_returns_provider_stations():
    stations = [{"code": "NDLS", "name": "New Delhi", "city": "Delhi"}]
    with patch.object(rail_service, "find_stations", new=AsyncMock(return_value=(stations, None))):
        r = client.get("/api/transport/stations", params={"q": "Delhi"})
    assert r.status_code == 200 and r.json()["stations"][0]["code"] == "NDLS"


def test_station_search_without_key_never_invents_stations():
    rail_service._station_cache.clear()
    with patch.object(rail_service.client, "search_stations", new=AsyncMock(side_effect=RuntimeError("RAILRADAR_API_KEY is not configured."))):
        stations, notice = asyncio.run(rail_service.find_stations("Atlantis"))
    assert stations == [] and "unavailable" in notice.lower()


# ------------------------------------------------------------------ nearby dates for flights
def test_price_tiers_green_orange_red():
    t = classify_price_tiers({"d1": 3000, "d2": 4500, "d3": 6000, "d4": None})
    assert t == {"d1": "low", "d2": "medium", "d3": "high", "d4": "unknown"}
    assert classify_price_tiers({"a": 5000}) == {"a": "medium"}
    assert classify_price_tiers({"a": 5000, "b": 5000}) == {"a": "medium", "b": "medium"}


def test_date_note_points_to_the_cheaper_day():
    note = build_date_note([{"date": "2026-11-03", "cheapest_price": 4000},
                            {"date": "2026-11-04", "cheapest_price": 5200}], "2026-11-04")
    assert "03 Nov" in note and "₹1,200" in note
    same = build_date_note([{"date": "2026-11-03", "cheapest_price": 6000},
                            {"date": "2026-11-04", "cheapest_price": 5200}], "2026-11-04")
    assert "lowest fare" in same


def _flight(price):
    return TransportOption(id=f"f{price}", mode="flight", provider="serpapi_google_flights", operator="Air",
                           origin="DEL", destination="BOM", departure_time="x", arrival_time="y",
                           duration_minutes=120, price=price)


def test_flight_dates_cover_two_days_either_side_and_colour_by_price():
    centre = date.today() + timedelta(days=20)
    by_date = {(centre + timedelta(days=o)).isoformat(): p for o, p in
               zip(range(-2, 3), (6500, 4000, 5200, 5100, None))}

    async def fake_search(origin, dest, d, adults=1, currency="INR"):
        p = by_date[d]
        return ([_flight(p)] if p else []), None

    with patch("app.services.transport_search_service.flight_service.search_flights", new=fake_search):
        res = asyncio.run(transport_search_service.flight_date_prices("Delhi", "Mumbai", centre.isoformat(), 1, "INR"))
    assert [d.date for d in res.days] == list(by_date)
    tiers = {d.date: d.tier for d in res.days}
    assert tiers[(centre - timedelta(days=1)).isoformat()] == "low"
    assert tiers[(centre - timedelta(days=2)).isoformat()] == "high"
    assert tiers[(centre + timedelta(days=2)).isoformat()] == "unknown"
    assert [d.is_selected for d in res.days].count(True) == 1
    assert "cheaper" in res.note


def test_return_leg_dates_before_the_outbound_date_are_not_offered():
    centre = date.today() + timedelta(days=20)

    async def fake_search(origin, dest, d, adults=1, currency="INR"):
        return [_flight(5000)], None

    with patch("app.services.transport_search_service.flight_service.search_flights", new=fake_search):
        res = asyncio.run(transport_search_service.flight_date_prices(
            "Mumbai", "Delhi", centre.isoformat(), 1, "INR", earliest_date=(centre - timedelta(days=1)).isoformat()))
    assert min(d.date for d in res.days) == (centre - timedelta(days=1)).isoformat()
    assert len(res.days) == 4


def test_flight_dates_endpoint_validates_input():
    base = {"origin": "Delhi", "destination": "Mumbai", "date": (date.today() + timedelta(days=9)).isoformat()}
    assert client.post("/api/transport/flight-dates", json={**base, "destination": "delhi"}).status_code == 422
    assert client.post("/api/transport/flight-dates", json={**base, "date": "2001-01-01"}).status_code == 422
    assert client.post("/api/transport/flight-dates", json={**base, "date": "nope"}).status_code == 422


def test_search_leg_endpoint_rejects_past_dates():
    r = client.post("/api/transport/search-leg", json={"origin": "Delhi", "destination": "Mumbai", "date": "2001-01-01"})
    assert r.status_code == 422
