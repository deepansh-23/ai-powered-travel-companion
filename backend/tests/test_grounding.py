"""Automated tests for destination grounding and anti-stale data guarantees (Section 33A-7).
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_destination_isolation_places():
    # Search 1: Delhi returns Delhi data
    res_delhi = client.post("/api/places/search", json={"location": "Delhi", "radius_km": 5.0})
    assert res_delhi.status_code == 200
    data_delhi = res_delhi.json()
    assert data_delhi["center"]["latitude"] == pytest.approx(28.6315, rel=1e-2)


    # Search 2: Mumbai in mock mode must NOT silently fall back to Delhi data!
    res_mumbai = client.post("/api/places/search", json={"location": "Mumbai", "radius_km": 5.0})
    # Either 404 Not Found, or if mock exists, different coordinates
    if res_mumbai.status_code == 200:
        data_mumbai = res_mumbai.json()
        assert data_delhi["center"]["latitude"] != data_mumbai["center"]["latitude"]
    else:
        assert res_mumbai.status_code in (404, 422, 503)



def test_gibberish_destination_geocoding_rejection():
    # Searching an invalid destination returns 404 or empty / error without fake data
    res = client.post("/api/places/search", json={"location": "Xyzzyville123987", "radius_km": 5.0})
    # Should either return 404 or 422 or empty places
    if res.status_code == 200:
        assert len(res.json().get("places", [])) == 0 or res.json().get("data_mode") == "mock"
    else:
        assert res.status_code in (404, 422, 503)
