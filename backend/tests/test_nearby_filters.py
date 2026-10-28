"""Places / cafes / medical: the chip counts must describe exactly the places that were returned,
so a filter chip can never promise more than it shows."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("limit", [3, 7, 30, 100])
def test_place_chip_counts_match_the_returned_places(limit):
    d = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 8.0, "limit": limit}).json()
    seen = {}
    for p in d["places"]:
        seen[p["category"]] = seen.get(p["category"], 0) + 1
    assert d["counts_by_category"] == seen and sum(seen.values()) == len(d["places"]) == d["total"] <= limit


@pytest.mark.parametrize("limit", [2, 30])
def test_cafe_amenity_counts_match_the_returned_cafes(limit):
    d = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 5.0, "limit": limit}).json()
    seen = {}
    for c in d["cafes"]:
        for a in c["amenities"]:
            seen[a] = seen.get(a, 0) + 1
    assert d["counts_by_amenity"] == seen


@pytest.mark.parametrize("limit", [4, 30])
def test_medical_service_type_counts_match_the_returned_facilities(limit):
    d = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": 8.0, "limit": limit}).json()
    seen = {}
    for m in d["medical"]:
        seen[m["service_type"]] = seen.get(m["service_type"], 0) + 1
    assert d["counts_by_service_type"] == seen and len(d["medical"]) <= limit


def test_every_chip_selects_exactly_the_number_it_shows():
    d = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 8.0, "limit": 5}).json()
    for cat, n in d["counts_by_category"].items():
        assert len([p for p in d["places"] if p["category"] == cat]) == n
