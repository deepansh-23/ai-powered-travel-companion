"""RailRadar parsing/URL tests using a saved fixture (no live API calls)."""

import asyncio

from app.services.rail_service import RailRadarClient, rail_service

FIXTURE = {
    "success": True,
    "data": {
        "from": {"code": "NDLS", "name": "New Delhi"},
        "to": {"code": "ASR", "name": "Amritsar Junction"},
        "count": 2,
        "trains": [
            {
                "train": {"number": "12013", "name": "Amritsar Shatabdi", "type": "Shatabdi", "runDays": ["mon"]},
                "from": {"departure": "07:20", "day": 1, "sequence": 1},
                "to": {"arrival": "13:55", "day": 1, "sequence": 9},
                "distance": 449.0,
                "duration": 395,
                "totalHaltsBetween": 4,
            },
            {
                "train": {"number": "12460", "name": "NDLS ASR Intercity", "type": "Express"},
                "from": {"departure": "", "day": 1},
                "to": {"arrival": "", "day": 1},
                "duration": 400,
            },
        ],
    },
}


def test_parse_railradar_documented_shape():
    opts = rail_service.parse_railradar_response(FIXTURE, "NDLS", "ASR")
    # entry without times is skipped, not invented
    assert len(opts) == 1
    o = opts[0]
    assert o.mode == "train" and o.provider == "railradar"
    assert o.number == "12013"
    assert "Amritsar Shatabdi" in o.operator
    assert o.departure_time == "07:20" and o.arrival_time == "13:55"
    assert o.duration_minutes == 395 and o.duration_formatted == "6h 35m"
    assert o.stops == 4
    # RailRadar returns no fare / booking URL: never fabricated
    assert o.price is None and o.booking_url is None


def test_parse_railradar_empty_or_malformed():
    assert rail_service.parse_railradar_response({}, "A", "B") == []
    assert rail_service.parse_railradar_response({"data": {"trains": "x"}}, "A", "B") == []


def test_station_resolution_is_exact():
    assert rail_service.resolve_station_code("Amritsar") == "ASR"
    assert rail_service.resolve_station_code("NDLS") == "NDLS"
    # partial / unknown names must not silently map to a station
    assert rail_service.resolve_station_code("Amrit") is None
    assert rail_service.resolve_station_code("Xyzzyville") is None


def test_railradar_request_url(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return FIXTURE

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None, params=None):
            captured.update(url=url, headers=headers, params=params)
            return FakeResp()

    monkeypatch.setattr("app.services.rail_service.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(RailRadarClient, "_get_api_key", lambda self: "test-key")
    asyncio.run(RailRadarClient().get_trains_between_stations("NDLS", "ASR", "2026-11-10"))
    assert captured["url"] == "https://api.railradar.in/v1/trains/between/NDLS/ASR"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["params"] == {"date": "2026-11-10"}
