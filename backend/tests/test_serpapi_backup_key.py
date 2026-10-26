"""SerpApi backup key (SERP_API_KEY2): switches when the first key is out of searches or rejected.

All HTTP is faked: no network and no SerpApi credits. The fake keeps a script per key.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import settings
from app.models.transport import TransportSearchRequest
from app.services import flight_service as fs
from app.services import serpapi_client as sc
from app.services.rail_service import rail_service
from app.services.transport_search_service import transport_search_service

KEY1, KEY2 = "MAIN-KEY-aaaaaaaaaaaaaaaaaaaa", "BACKUP-KEY-bbbbbbbbbbbbbbbbbbb"
FLIGHTS = {"best_flights": [{"flights": [{
    "departure_airport": {"name": "Delhi", "id": "DEL", "time": "2099-03-10 06:00"},
    "arrival_airport": {"name": "Mumbai", "id": "BOM", "time": "2099-03-10 08:10"},
    "duration": 130, "airline": "TestAir", "flight_number": "TA 1", "travel_class": "Economy"}],
    "total_duration": 130, "price": 4100, "type": "One way"}], "other_flights": []}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else FLIGHTS

    def json(self):
        return self._body


class FakeHttp:
    """script: {key: Resp | Exception | callable}. Records which key each request used."""
    def __init__(self, script):
        self.script, self.used = script, []

    def factory(self):
        outer = self

        class Client:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url, params=None):
                key = params["api_key"]
                outer.used.append(key)
                item = outer.script[key]
                if isinstance(item, Exception):
                    raise item
                return item
        return Client


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", KEY1)
    monkeypatch.setattr(settings, "SERP_API_KEY2", KEY2)
    c = sc.SerpApiClient()
    monkeypatch.setattr(sc, "serpapi_client", c)
    monkeypatch.setattr(fs, "serpapi_client", c)
    return c


def _go(client, fake, params=None, monkeypatch=None):
    with patch.object(sc.httpx, "AsyncClient", fake.factory()):
        return asyncio.run(client.search(params or {"engine": "google_flights", "q": "x"}))


PARAMS = {"engine": "google_flights", "departure_id": "DEL", "arrival_id": "BOM", "outbound_date": "2099-03-10", "type": "2"}


# ------------------------------------------------------------------ switching
@pytest.mark.parametrize("first", [
    Resp(429, {}),                                                       # HTTP 429: out of searches / rate limited
    Resp(200, {"error": "Your account has run out of searches."}),     # JSON quota error
    Resp(401, {}),                                                       # key rejected
    Resp(200, {"error": "Invalid API key. Your API key should be here: https://serpapi.com/manage-api-key"}),
])
def test_switches_to_the_backup_key_when_the_first_is_exhausted_or_rejected(client, first):
    fake = FakeHttp({KEY1: first, KEY2: Resp()})
    assert _go(client, fake, PARAMS)["best_flights"][0]["price"] == 4100
    assert fake.used == [KEY1, KEY2]


def test_exhausted_key_rests_so_later_searches_go_straight_to_the_backup(client):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp()})
    _go(client, fake, PARAMS)
    _go(client, fake, dict(PARAMS, outbound_date="2099-03-11"))
    _go(client, fake, dict(PARAMS, outbound_date="2099-03-12"))
    assert fake.used == [KEY1, KEY2, KEY2, KEY2]                          # no wasted attempt on the used-up key


def test_main_key_is_tried_again_after_its_rest_period(client, monkeypatch):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp()})
    _go(client, fake, PARAMS)
    fake.script[KEY1] = Resp()                                            # new month: the main key works again
    real_time = sc.time.time
    monkeypatch.setattr(sc.time, "time", lambda: real_time() + sc.QUOTA_COOLDOWN_SECONDS + 5)
    _go(client, fake, dict(PARAMS, outbound_date="2099-03-11"))
    assert fake.used[-1] == KEY1


def test_cached_results_are_shared_between_keys(client):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp()})
    _go(client, fake, PARAMS)
    _go(client, fake, PARAMS)                                             # identical search: served from the cache
    assert fake.used == [KEY1, KEY2]


def test_when_every_key_is_exhausted_the_original_error_is_raised_and_each_key_tried_once(client):
    fake = FakeHttp({KEY1: Resp(200, {"error": "Your account has run out of searches."}), KEY2: Resp(429, {})})
    with pytest.raises(RuntimeError, match="quota"):
        _go(client, fake, PARAMS)
    assert fake.used == [KEY1, KEY2]


# ------------------------------------------------------------------ no switching for problems that are not the key
@pytest.mark.parametrize("first", [
    Resp(500, {}),
    Resp(200, {"error": "Google hasn't returned any results for this query."}),
    Resp(200, {"error": "Invalid departure_id parameter"}),               # a bad request, not a bad key
    httpx.ConnectTimeout("slow"),
])
def test_server_errors_timeouts_and_bad_requests_do_not_burn_the_backup_key(client, first):
    fake = FakeHttp({KEY1: first, KEY2: Resp()})
    with pytest.raises(RuntimeError):
        _go(client, fake, PARAMS)
    assert fake.used == [KEY1]


# ------------------------------------------------------------------ configuration
def test_only_the_main_key_behaves_exactly_as_before(client, monkeypatch):
    monkeypatch.setattr(settings, "SERP_API_KEY2", None)
    fake = FakeHttp({KEY1: Resp(429, {})})
    with pytest.raises(RuntimeError, match="quota exceeded"):
        _go(client, fake, PARAMS)
    assert fake.used == [KEY1]


def test_backup_key_alone_is_enough_and_placeholders_or_duplicates_are_ignored(client, monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "your_serpapi_api_key_here")
    fake = FakeHttp({KEY2: Resp()})
    assert _go(client, fake, PARAMS)["best_flights"]
    assert fake.used == [KEY2]
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", KEY2)                # same key twice: never "switch" to itself
    assert client._configured_keys() == [KEY2]


def test_no_key_at_all_gives_the_same_clear_error(client, monkeypatch):
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", None)
    monkeypatch.setattr(settings, "SERP_API_KEY2", "")
    with pytest.raises(RuntimeError, match="Missing or unconfigured SERPAPI_API_KEY"):
        asyncio.run(client.search(PARAMS))


def test_keys_never_appear_in_logs_or_errors(client, caplog):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp(429, {})})
    caplog.set_level(logging.DEBUG)
    with pytest.raises(RuntimeError) as err:
        _go(client, fake, PARAMS)
    text = caplog.text + str(err.value)
    assert KEY1 not in text and KEY2 not in text and "switching to the backup key" in text


def test_the_setting_is_read_from_SERP_API_KEY2_and_cleaned_like_the_other_keys(monkeypatch):
    monkeypatch.setenv("SERP_API_KEY2", "  'abc123'  ")
    assert settings.__class__().SERP_API_KEY2 == "abc123"
    monkeypatch.setenv("SERP_API_KEY2", "   ")
    assert settings.__class__().SERP_API_KEY2 is None


# ------------------------------------------------------------------ flight search keeps working end to end
def test_flight_search_returns_results_through_the_backup_key_and_the_page_does_not_crash(client):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp()})
    req = TransportSearchRequest(source="Delhi", destination="Mumbai", outbound_date="2099-03-10", travelers=1)
    with patch.object(sc.httpx, "AsyncClient", fake.factory()), \
         patch.object(rail_service, "search_trains", new=AsyncMock(return_value=([], None))):
        res = asyncio.run(transport_search_service.search_transport(req))
    assert len(res.outbound.flights) == 1 and res.outbound.flights[0].price == 4100
    assert res.outbound.airport_notice is None
    assert fake.used == [KEY1, KEY2]


def test_flight_search_reports_a_notice_not_a_crash_when_both_keys_are_exhausted(client):
    fake = FakeHttp({KEY1: Resp(429, {}), KEY2: Resp(429, {})})
    req = TransportSearchRequest(source="Delhi", destination="Mumbai", outbound_date="2099-03-10", travelers=1)
    with patch.object(sc.httpx, "AsyncClient", fake.factory()), \
         patch.object(rail_service, "search_trains", new=AsyncMock(return_value=([], None))):
        res = asyncio.run(transport_search_service.search_transport(req))
    assert res.outbound.flights == [] and "Flights unavailable" in res.outbound.airport_notice
