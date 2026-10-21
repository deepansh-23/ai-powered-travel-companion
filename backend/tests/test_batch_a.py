"""Batch A: several local transport modes, and the planner staying login-only."""

from fastapi.testclient import TestClient

from app.main import app
from app.models.itinerary import FinalizeRequest, ItineraryRequest, normalize_transport_modes
from app.services.directions_service import suggest_mode

client = TestClient(app)

BASE = {"destination": "Goa", "source": "Delhi", "departure_date": "2099-03-10", "return_date": "2099-03-12",
        "duration_days": 3, "budget_per_person_per_day": 3000, "travelers_count": 2}


def test_transport_modes_are_cleaned():
    assert normalize_transport_modes(["Walking", "driving", "bogus"]) == ["walking", "taxi"]
    assert normalize_transport_modes(["taxi", "public", "walking"]) == ["walking", "public", "taxi"]
    assert normalize_transport_modes(None) is None and normalize_transport_modes(["bogus"]) is None
    assert ItineraryRequest(**BASE, transport_modes=["Transit"]).transport_modes == ["public"]


def test_each_leg_uses_the_best_of_the_ticked_modes():
    assert suggest_mode(0.8, ["walking", "taxi"])[0] == "Walk"
    assert suggest_mode(5, ["walking", "taxi"])[0] == "Taxi / Auto-rickshaw"
    assert suggest_mode(5, ["walking"])[0] == "Walk"
    assert suggest_mode(2, ["public", "taxi"])[1] == "driving"
    assert suggest_mode(8, ["public", "taxi"])[1] == "transit"
    # the old single-choice values still behave as before
    assert suggest_mode(2.0, "public")[0] == "Auto-rickshaw / e-rickshaw"
    assert suggest_mode(0.3, "driving")[0] == "Walk"


def test_generate_accepts_several_modes_and_finalize_keeps_them():
    r = client.post("/api/itinerary/generate", json={**BASE, "transport_modes": ["walking", "taxi"]})
    assert r.status_code == 200, r.text
    plan = r.json()
    r2 = client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": [], "travelers_count": 2,
                                                      "transport_modes": ["walking", "taxi"]})
    assert r2.status_code == 200, r2.text
    assert FinalizeRequest(itinerary=plan, transport_modes=["driving"]).transport_modes == ["taxi"]
