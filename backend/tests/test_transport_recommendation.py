"""Automated tests for deterministic Transport Recommendation scoring (Section 33A-3).
"""

import pytest
from app.models.transport import TransportOption
from app.services.transport_recommendation_service import transport_recommendation_service


@pytest.fixture
def transport_fixtures():
    # 1: Cheap and slow (e.g. Sleeper train, low fare, long duration)
    cheap_slow = TransportOption(
        id="opt_cheap_slow",
        mode="train",
        provider="railradar",
        operator="Indian Railways Sleeper",
        origin="NDLS",
        destination="ASR",
        departure_time="2026-10-15 07:00",
        arrival_time="2026-10-15 15:30",
        duration_minutes=510,
        stops=5,
        price=350.0,
        currency="INR"
    )

    # 2: Expensive and fast (e.g. Direct Flight, high price, 70 min duration)
    fast_expensive = TransportOption(
        id="opt_fast_expensive",
        mode="flight",
        provider="serpapi_google_flights",
        operator="IndiGo Express",
        origin="DEL",
        destination="ATQ",
        departure_time="2026-10-15 08:00",
        arrival_time="2026-10-15 09:10",
        duration_minutes=70,
        stops=0,
        price=4800.0,
        currency="INR"
    )

    # 3: Balanced option (e.g. Vande Bharat Express, moderate price, moderate duration, direct)
    balanced = TransportOption(
        id="opt_balanced",
        mode="train",
        provider="railradar",
        operator="Vande Bharat Express",
        origin="NDLS",
        destination="ASR",
        departure_time="2026-10-15 15:15",
        arrival_time="2026-10-15 20:45",
        duration_minutes=330,
        stops=0,
        price=1200.0,
        currency="INR"
    )

    return [cheap_slow, fast_expensive, balanced]


def test_cheapest_recommendation(transport_fixtures):
    scored = transport_recommendation_service.score_options(transport_fixtures, preference="cheapest")
    top = scored[0]
    assert top.id == "opt_cheap_slow"
    assert top.price == 350.0
    assert top.recommendation_badge == "Cheapest"
    assert len(top.recommendation_reason) > 0


def test_fastest_recommendation(transport_fixtures):
    scored = transport_recommendation_service.score_options(transport_fixtures, preference="fastest")
    top = scored[0]
    assert top.id == "opt_fast_expensive"
    assert top.duration_minutes == 70
    assert top.recommendation_badge == "Fastest"
    assert len(top.recommendation_reason) > 0


def test_best_overall_recommendation(transport_fixtures):
    scored = transport_recommendation_service.score_options(transport_fixtures, preference="best-overall")
    top = scored[0]
    assert top.id == "opt_balanced"
    assert top.recommendation_badge == "Best Overall"
    assert len(top.recommendation_reason) > 0


def test_no_preference_recommendation(transport_fixtures):
    scored = transport_recommendation_service.score_options(transport_fixtures, preference="no-preference")
    top = scored[0]
    assert top.id == "opt_balanced"
    assert len(top.recommendation_reason) > 0


def test_prefer_flight_mode_bonus():
    # Two options with very similar travel times / prices
    flt = TransportOption(
        id="flt_1", mode="flight", provider="serpapi_google_flights", operator="Air India",
        origin="DEL", destination="BOM", departure_time="10:00", arrival_time="12:00",
        duration_minutes=120, stops=0, price=3000.0, currency="INR"
    )
    trn = TransportOption(
        id="trn_1", mode="train", provider="railradar", operator="Tejas Express",
        origin="DEL", destination="BOM", departure_time="10:00", arrival_time="12:00",
        duration_minutes=120, stops=0, price=3000.0, currency="INR"
    )
    scored = transport_recommendation_service.score_options([trn, flt], preference="prefer-flight")
    assert scored[0].id == "flt_1"
    assert scored[0].recommendation_badge == "Top Flight Pick"
    assert "Flight preferred" in scored[0].recommendation_reason


def test_prefer_train_mode_bonus():
    flt = TransportOption(
        id="flt_1", mode="flight", provider="serpapi_google_flights", operator="Air India",
        origin="DEL", destination="BOM", departure_time="10:00", arrival_time="12:00",
        duration_minutes=120, stops=0, price=3000.0, currency="INR"
    )
    trn = TransportOption(
        id="trn_1", mode="train", provider="railradar", operator="Tejas Express",
        origin="DEL", destination="BOM", departure_time="10:00", arrival_time="12:00",
        duration_minutes=120, stops=0, price=3000.0, currency="INR"
    )
    scored = transport_recommendation_service.score_options([flt, trn], preference="prefer-train")
    assert scored[0].id == "trn_1"
    assert scored[0].recommendation_badge == "Top Train Pick"
    assert "Train preferred" in scored[0].recommendation_reason


def test_all_options_have_reasons(transport_fixtures):
    for pref in ["cheapest", "fastest", "best-overall", "prefer-flight", "prefer-train", "no-preference"]:
        scored = transport_recommendation_service.score_options(transport_fixtures, preference=pref)
        for opt in scored:
            assert opt.recommendation_reason is not None
            assert len(opt.recommendation_reason.strip()) > 0
