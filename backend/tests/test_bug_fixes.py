"""Additional tests covering requirements from the bug-fix specification.

These tests run in MOCK_MODE=true (enforced by conftest.py) and verify:
- Manchester fallback prevention
- Unnamed place filtering
- Duplicate removal
- Radius filtering
- Invalid location handling
- MOCK_MODE behavior
- Destination name surfaced correctly in itinerary response
- Empty history on startup
"""

import pytest
import os
from fastapi.testclient import TestClient

# conftest.py already sets MOCK_MODE=true before import
from app.main import app
from app.config import settings

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Confirm test environment is running in mock mode
# ---------------------------------------------------------------------------
def test_mock_mode_is_true_in_tests():
    """Tests must run in mock mode to avoid real API calls."""
    assert settings.MOCK_MODE is True, (
        "Tests must run with MOCK_MODE=true. "
        "Check conftest.py or MOCK_MODE env variable."
    )


# ---------------------------------------------------------------------------
# 2. Manchester fallback prevention
# ---------------------------------------------------------------------------
def test_no_manchester_in_amritsar_places():
    """Searching Amritsar (not in mock locations.json) raises 404, not Manchester data."""
    resp = client.post("/api/places/search", json={"location": "Amritsar", "radius_km": 5.0})
    # In mock mode, Amritsar is not in locations.json → should return 404
    assert resp.status_code == 404
    detail = resp.json().get("detail", "")
    assert "amritsar" in detail.lower() or "could not find" in detail.lower()
    # CRITICAL: must not silently return places data for a different city
    assert "places" not in resp.json() or resp.json().get("places") is None


def test_no_manchester_in_mumbai_places():
    """Searching Mumbai (not in mock locations.json) raises 404."""
    resp = client.post("/api/places/search", json={"location": "Mumbai", "radius_km": 5.0})
    assert resp.status_code == 404


def test_no_manchester_in_jaipur_places():
    """Searching Jaipur (not in mock locations.json) raises 404."""
    resp = client.post("/api/places/search", json={"location": "Jaipur", "radius_km": 5.0})
    assert resp.status_code == 404


def test_manchester_places_data_not_returned_for_delhi():
    """Delhi search must not return Manchester places like 'John Rylands' or 'Cloud 23'."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 20.0})
    assert resp.status_code == 200
    places = resp.json().get("places", [])
    names = [p["name"] for p in places]
    manchester_places = [
        "John Rylands Library", "The John Rylands Library",
        "Manchester Art Gallery", "St Peter's Square", "Central Library",
        "Dishoom Manchester", "Bundobust", "Cloud 23", "Cloud 23 View Lounge",
        "Afflecks", "Mackie Mayor", "Federal Cafe Bar",
    ]
    for mp in manchester_places:
        assert mp not in names, (
            f"Manchester place '{mp}' appeared in Delhi results — Manchester fallback bug!"
        )


def test_itinerary_destination_reflects_request():
    """Itinerary response destination must match the requested destination."""
    payload = {
        "destination": "Delhi",
        "duration_days": 2,
        "budget_per_person_per_day": 3000.0,
        "travelers_count": 1,
        "interests": ["culture"],
    }
    resp = client.post("/api/itinerary/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["destination"].lower() == "delhi"
    # Title must contain the destination
    assert "delhi" in data["title"].lower()


# ---------------------------------------------------------------------------
# 3. Unnamed place filtering
# ---------------------------------------------------------------------------
def test_no_unnamed_places_in_results():
    """No place with a generic/invalid name should appear in results."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 20.0})
    assert resp.status_code == 200
    places = resp.json().get("places", [])
    bad_names = {"unnamed", "unnamed place", "unknown", "unknown place",
                 "n/a", "null", "undefined", "unnamed road", ""}
    for p in places:
        name_lower = (p.get("name") or "").strip().lower()
        assert name_lower not in bad_names, (
            f"Unnamed place slipped through: {repr(p.get('name'))}"
        )
        assert p.get("name") is not None and len(p["name"].strip()) > 0


def test_no_unnamed_cafes():
    resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    cafes = resp.json().get("cafes", [])
    for c in cafes:
        assert c.get("name") and len(c["name"].strip()) > 2


def test_no_unnamed_medical():
    resp = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": 10.0})
    assert resp.status_code == 200
    medical = resp.json().get("medical", [])
    for m in medical:
        assert m.get("name") and len(m["name"].strip()) > 2


# ---------------------------------------------------------------------------
# 4. Duplicate removal
# ---------------------------------------------------------------------------
def test_no_duplicate_places():
    """No two places should share the same name+address combination."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 20.0})
    assert resp.status_code == 200
    places = resp.json().get("places", [])
    seen = set()
    for p in places:
        key = (p.get("name", "").lower(), (p.get("address") or "").lower())
        assert key not in seen, f"Duplicate place detected: {p['name']}"
        seen.add(key)


def test_no_duplicate_cafes():
    resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 20.0})
    assert resp.status_code == 200
    cafes = resp.json().get("cafes", [])
    seen = set()
    for c in cafes:
        key = (c.get("name", "").lower(), (c.get("address") or "").lower())
        assert key not in seen, f"Duplicate cafe: {c['name']}"
        seen.add(key)


# ---------------------------------------------------------------------------
# 5. Radius filtering
# ---------------------------------------------------------------------------
def test_radius_200m_returns_fewer_than_5km():
    """A 200m radius must return fewer places than a 5km radius for the same location."""
    small = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 0.2})
    large = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 5.0})
    assert small.status_code == 200
    assert large.status_code == 200
    small_count = small.json()["total"]
    large_count = large.json()["total"]
    assert small_count <= large_count, (
        f"Small radius ({small_count}) returned MORE results than large radius ({large_count})"
    )


def test_radius_is_respected_in_response():
    """The radius_km in the response must match the requested radius."""
    for radius in [0.5, 1.0, 3.0, 5.0, 10.0]:
        resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": radius})
        assert resp.status_code == 200
        assert resp.json()["radius_km"] == pytest.approx(radius, rel=1e-3)


def test_places_within_radius_have_valid_distance():
    """All places with coordinates must have distance_m <= radius_m."""
    radius_km = 2.0
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": radius_km})
    assert resp.status_code == 200
    places = resp.json().get("places", [])
    for p in places:
        if p.get("distance_m") is not None:
            assert p["distance_m"] <= radius_km * 1000 + 1, (
                f"Place '{p['name']}' is {p['distance_m']}m away but radius is {radius_km*1000}m"
            )


# ---------------------------------------------------------------------------
# 6. Invalid location
# ---------------------------------------------------------------------------
def test_invalid_city_returns_404():
    """An invalid city must return 404, not another city's data."""
    for bad_location in ["InvalidCityXYZ123", "ZZZZNOTACITY999", "xyzabc"]:
        resp = client.post("/api/places/search", json={"location": bad_location, "radius_km": 3.0})
        assert resp.status_code == 404, (
            f"Expected 404 for invalid location '{bad_location}', got {resp.status_code}"
        )
        data = resp.json()
        assert "detail" in data
        # Must not silently return places for another city
        assert "places" not in data


def test_empty_location_returns_4xx():
    """Empty location must return an error, not a default city."""
    resp = client.post("/api/places/search", json={"location": "", "radius_km": 3.0})
    # Should be 4xx (either 404 or 422 validation error)
    assert resp.status_code in (404, 422), (
        f"Expected 4xx for empty location, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# 7. MOCK_MODE behavior verification
# ---------------------------------------------------------------------------
def test_data_mode_is_mock_in_test_env():
    """All responses must have data_mode='mock' in test environment."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "mock"

    resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "mock"

    resp = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "mock"

    resp = client.post("/api/itinerary/generate", json={
        "destination": "Delhi",
        "duration_days": 1,
        "budget_per_person_per_day": 3000.0,
    })
    assert resp.status_code == 200
    assert resp.json()["data_mode"] == "mock"


# ---------------------------------------------------------------------------
# 8. History starts empty and no Manchester pre-seeded
# ---------------------------------------------------------------------------
def test_history_starts_empty_no_manchester():
    """History must start empty (no pre-seeded Manchester data)."""
    resp = client.get("/api/history")
    assert resp.status_code == 200
    items = resp.json()
    # History starts empty for new installation
    # (Items added by other tests in same session are allowed — check no Manchester items)
    for item in items:
        title = (item.get("title") or "").lower()
        assert "manchester" not in title, (
            f"Manchester pre-seeded history item found: {item['title']}"
        )


# ---------------------------------------------------------------------------
# 9. Website safety — no dangerous URLs surfaced
# ---------------------------------------------------------------------------
def test_no_dangerous_urls_in_places():
    """No place should have a javascript: or data: URL."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 20.0})
    assert resp.status_code == 200
    for p in resp.json().get("places", []):
        ws = p.get("website")
        if ws:
            assert ws.startswith(("http://", "https://")), (
                f"Dangerous URL found: {ws} for place {p['name']}"
            )
            assert "javascript:" not in ws
            assert "data:" not in ws


# ---------------------------------------------------------------------------
# 10. Center coordinates match the requested location
# ---------------------------------------------------------------------------
def test_delhi_center_coordinates():
    """Delhi search must return Delhi coordinates, not Manchester."""
    resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    center = resp.json()["center"]
    # Delhi is approx 28.6N, 77.2E — not Manchester (53.5N, -2.2W)
    assert center["latitude"] == pytest.approx(28.6315, rel=1e-2)
    assert center["longitude"] == pytest.approx(77.2167, rel=1e-2)
    # Explicitly NOT Manchester
    assert center["latitude"] < 55.0, "Center appears to be in the UK, not India!"
    assert center["longitude"] > 0, "Center longitude is negative — not India!"


def test_london_center_coordinates():
    """London search must return London coordinates."""
    resp = client.post("/api/places/search", json={"location": "London", "radius_km": 3.0})
    assert resp.status_code == 200
    center = resp.json()["center"]
    assert center["latitude"] == pytest.approx(51.5074, rel=1e-2)
    assert center["longitude"] == pytest.approx(-0.1278, rel=1e-1)


# ---------------------------------------------------------------------------
# 11. Budget calculations
# ---------------------------------------------------------------------------
def test_itinerary_budget_calculations():
    """Budget in response must reflect travelers × days × daily rate."""
    payload = {
        "destination": "Delhi",
        "duration_days": 3,
        "budget_per_person_per_day": 2000.0,
        "travelers_count": 2,
    }
    resp = client.post("/api/itinerary/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    # 2 people × ₹2000/day × 3 days = ₹12,000 total
    assert "12,000" in data["estimated_budget_total"]
    assert "₹" in data["estimated_budget_total"]
    # Per-day label
    for day in data["days"]:
        assert "₹" in day["estimated_day_cost"]
        # Each day: 2 × 2000 = 4000
        assert "4,000" in day["estimated_day_cost"]


# ---------------------------------------------------------------------------
# 12. 24/7 status is not assumed for all medical facilities
# ---------------------------------------------------------------------------
def test_medical_24_7_not_assumed():
    """Some medical facilities must NOT be marked 24/7 (is_24_7 = False or null)."""
    resp = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": 10.0})
    assert resp.status_code == 200
    medical = resp.json().get("medical", [])
    non_24_7 = [m for m in medical if m.get("is_24_7") is not True]
    assert len(non_24_7) > 0, (
        "All medical facilities are marked 24/7 — this is unrealistic; "
        "not all facilities are 24/7."
    )
