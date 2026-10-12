"""Regression tests for Area Guide endpoint (Section 10 & 23).

This test exists specifically to catch the regression where the route
calls ai_service.summarize_area() but the method did not exist on
AIService, resulting in an AttributeError at runtime.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_area_summarize_mock():
    """POST /api/area/summarize should succeed in mock mode and return
    a structurally valid AreaSummarizeResponse."""
    payload = {"area": "Manchester City Centre", "radius_km": 3.0}
    resp = client.post("/api/area/summarize", json=payload)
    assert resp.status_code == 200, (
        f"Area summarize failed with {resp.status_code}: {resp.text}"
    )
    data = resp.json()

    # Required top-level fields
    assert data["area_name"], "area_name must be non-empty"
    assert data["data_mode"] == "mock"
    assert isinstance(data["sections"], dict)
    assert len(data["sections"]) > 0, "Area guide should have at least one section"

    # Quick facts structure
    qf = data["quick_facts"]
    for key in ("walkability", "transit_connectivity", "vibe", "best_for", "average_meal_cost"):
        assert key in qf, f"Missing quick_facts key: {key}"

    # Advantages, limitations, suitability are non-empty lists
    assert len(data["advantages"]) > 0
    assert len(data["limitations"]) > 0
    assert len(data["suitability"]) > 0


def test_area_summarize_unknown_area_mock():
    """Even for an area not in mock data, the endpoint should succeed
    and return a valid response (falling back to the first mock template)."""
    payload = {"area": "Nonexistent Village XYZ", "radius_km": 2.0}
    resp = client.post("/api/area/summarize", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["data_mode"] == "mock"
    assert data["area_name"], "area_name must be non-empty"


def test_area_summarize_validation():
    """Invalid payloads should be rejected with 422."""
    # Missing required 'area' field
    resp = client.post("/api/area/summarize", json={"radius_km": 3.0})
    assert resp.status_code == 422

    # Area too short
    resp = client.post("/api/area/summarize", json={"area": "X"})
    assert resp.status_code == 422
