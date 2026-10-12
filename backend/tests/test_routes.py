"""Integration tests for FastAPI endpoints (Section 23, 43, 50.7).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "smart-local-guide"


def test_places_search():
    payload = {
        "location": "Delhi",
        "radius_km": 6.0,
        "categories": ["museum", "hotel"]
    }
    response = client.post("/api/places/search", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "center" in data
    assert data["center"]["latitude"] == pytest.approx(28.6315, rel=1e-2)
    assert data["data_mode"] == "mock"
    assert "places" in data
    assert len(data["places"]) > 0

    # Test card integrity: first place
    first = data["places"][0]
    assert first["name"]
    assert first["category"] in ["museum", "hotel"]
    # Check that distance is calculated as an integer meters
    if first["distance_m"] is not None:
        assert isinstance(first["distance_m"], int)


def test_places_with_no_coords_and_invalid_website():
    # Search all categories with large radius
    payload = {"location": "Delhi", "radius_km": 20.0}
    response = client.post("/api/places/search", json=payload)
    data = response.json()
    places = data["places"]

    # Chandni Chowk Street Food Trail has no coordinates
    no_coord_place = next((p for p in places if p["name"] == "Chandni Chowk Street Food Trail"), None)
    assert no_coord_place is not None
    assert no_coord_place["latitude"] is None
    assert no_coord_place["longitude"] is None
    assert no_coord_place["distance_m"] is None

    # Purana Qila has a deliberately invalid raw website (javascript: scheme)
    # and must come back stripped to null, never surfaced as a link
    invalid_website_place = next((p for p in places if p["name"] == "Purana Qila (Old Fort)"), None)
    assert invalid_website_place is not None
    assert invalid_website_place["website"] is None

    # Invalid websites should be returned as None
    for p in places:
        if p["website"]:
            assert p["website"].startswith(("http://", "https://"))
            assert "javascript:" not in p["website"]
            assert "localhost" not in p["website"]


def test_route_calculation():
    # Origin: India Gate (28.6129, 77.2295)
    # Destination: National Museum (28.6117, 77.2194)
    payload = {
        "origin": {"latitude": 28.6129, "longitude": 77.2295},
        "destination": {"latitude": 28.6117, "longitude": 77.2194},
        "mode": "walking"
    }
    response = client.post("/api/route", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "geometry" in data
    assert data["geometry"]["type"] == "LineString"
    assert data["distance_m"] > 0
    assert "mode" in data
    assert "is_approximate" in data
    assert "summary" in data


def test_history_flow():
    # 1. List history
    response = client.get("/api/history")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    initial_count = len(items)

    # 2. Create history item
    new_item = {
        "feature_type": "places",
        "title": "Test Search",
        "preview": "Test search preview",
        "payload": {"test": True}
    }
    create_resp = client.post("/api/history", json=new_item)
    assert create_resp.status_code == 201
    created = create_resp.json()
    created_id = created["id"]

    # 3. Delete created item
    del_resp = client.delete(f"/api/history/{created_id}")
    assert del_resp.status_code == 200

    # 4. Check count restored
    after_resp = client.get("/api/history")
    assert len(after_resp.json()) == initial_count


def test_small_radius_search():
    for r in [0.2, 0.5]:
        places_resp = client.post("/api/places/search", json={"location": "Delhi", "radius_km": r})
        assert places_resp.status_code == 200, f"Places failed for radius {r}: {places_resp.text}"

        cafes_resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": r})
        assert cafes_resp.status_code == 200, f"Cafes failed for radius {r}: {cafes_resp.text}"

        med_resp = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": r})
        assert med_resp.status_code == 200, f"Medical failed for radius {r}: {med_resp.text}"


def test_itinerary_generate():
    payload = {
        "destination": "Delhi",
        "duration_days": 3,
        "budget_per_person_per_day": 4000.0,
        "travelers_count": 2,
        "interests": ["history", "food"]
    }
    resp = client.post("/api/itinerary/generate", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "INR"
    assert "₹" in data["estimated_budget_total"]
    assert len(data["days"]) == 3
    for d in data["days"]:
        assert "₹" in d["estimated_day_cost"]

    # Test out of bounds budget
    bad_resp = client.post("/api/itinerary/generate", json={"destination": "Delhi", "budget_per_person_per_day": 500})
    assert bad_resp.status_code == 422

    # Test food preferences and vegetarian food adaptation
    veg_payload = {
        "destination": "Delhi",
        "duration_days": 2,
        "budget_per_person_per_day": 3500.0,
        "travel_group_type": "family",
        "travelers_count": 4,
        "food_type": "vegetarian",
        "food_preferences": ["north-indian", "traditional-sweets"]
    }
    veg_resp = client.post("/api/itinerary/generate", json=veg_payload)
    assert veg_resp.status_code == 200
    veg_data = veg_resp.json()
    # 4 people * 3500 = 14000 per day
    assert "₹14,000" in veg_data["days"][0]["estimated_day_cost"]
    # Check that dinner is vegetarian (not steakhouse)
    dinner = veg_data["days"][0]["food_stop_dinner"]
    assert "steakhouse" not in dinner["cuisine"].lower()
    assert "vegetarian" in dinner["cuisine"].lower() or "vegetarian" in dinner["recommendation"].lower()


def test_cafes_outdoor_seating_filter():
    resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 3.0})
    assert resp.status_code == 200
    data = resp.json()
    assert "outdoor_seating" in data["counts_by_amenity"]
    assert data["counts_by_amenity"]["outdoor_seating"] >= 1
    # Filtering specifically by outdoor_seating returns only cafes with that amenity
    filtered_resp = client.post("/api/cafes/search", json={"location": "Delhi", "radius_km": 3.0, "amenities": ["outdoor_seating"]})
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()
    assert len(filtered_data["cafes"]) >= 1
    for cafe in filtered_data["cafes"]:
        assert "outdoor_seating" in cafe["amenities"]


def test_medical_all_service_types_present():
    resp = client.post("/api/medical/search", json={"location": "Delhi", "radius_km": 5.0})
    assert resp.status_code == 200
    data = resp.json()
    counts = data["counts_by_service_type"]
    required_services = [
        "24/7 hospitals",
        "Emergency departments",
        "Clinics",
        "Diagnostic centers",
        "Late-night pharmacies",
        "Urgent care"
    ]
    for service in required_services:
        assert service in counts, f"Missing service type: {service}"
        assert counts[service] >= 1, f"Zero count for service type: {service}"





