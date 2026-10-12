"""Automated tests for Transport and Hotel request validation (Section 33A-5).
"""

from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_validation_empty_source():
    payload = {
        "source": " ",
        "destination": "Amritsar",
        "outbound_date": (date.today() + timedelta(days=5)).isoformat(),
        "travelers": 1
    }
    res = client.post("/api/transport/search", json=payload)
    assert res.status_code == 422
    err_str = str(res.json()["detail"]).lower()
    assert "source" in err_str



def test_validation_identical_source_and_destination():
    payload = {
        "source": "Delhi",
        "destination": "delhi",
        "outbound_date": (date.today() + timedelta(days=5)).isoformat(),
        "travelers": 1
    }
    res = client.post("/api/transport/search", json=payload)
    assert res.status_code == 422
    assert "cannot be the same city" in res.json()["detail"]


def test_validation_past_date():
    payload = {
        "source": "Delhi",
        "destination": "Amritsar",
        "outbound_date": "2020-01-01",
        "travelers": 1
    }
    res = client.post("/api/transport/search", json=payload)
    assert res.status_code == 422
    assert "past" in res.json()["detail"]


def test_validation_return_before_departure():
    future_dep = (date.today() + timedelta(days=10)).isoformat()
    earlier_ret = (date.today() + timedelta(days=5)).isoformat()
    payload = {
        "source": "Delhi",
        "destination": "Amritsar",
        "outbound_date": future_dep,
        "return_date": earlier_ret,
        "travelers": 1
    }
    res = client.post("/api/transport/search", json=payload)
    assert res.status_code == 422
    assert "before outbound" in res.json()["detail"]


def test_validation_travelers_range():
    # Less than 1
    future_dep = (date.today() + timedelta(days=5)).isoformat()
    res = client.post("/api/transport/search", json={
        "source": "Delhi",
        "destination": "Amritsar",
        "outbound_date": future_dep,
        "travelers": 0
    })
    assert res.status_code == 422

    # More than 20
    res = client.post("/api/transport/search", json={
        "source": "Delhi",
        "destination": "Amritsar",
        "outbound_date": future_dep,
        "travelers": 25
    })
    assert res.status_code == 422
