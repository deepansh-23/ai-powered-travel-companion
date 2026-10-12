"""Automated tests for provider error mapping (Section 33A-6).
Simulates missing key, invalid key, quota, timeout, malformed JSON.
"""

from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.config import settings
from app.services.serpapi_client import SerpApiClient


@pytest.mark.asyncio
async def test_error_missing_api_key():
    client = SerpApiClient()
    with patch.object(settings, "SERPAPI_API_KEY", None):
        with pytest.raises(RuntimeError) as exc_info:
            await client.search({"engine": "google_flights"})
        assert "Missing or unconfigured SERPAPI_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_error_invalid_api_key_401():
    client = SerpApiClient()
    with patch.object(settings, "SERPAPI_API_KEY", "dummy_invalid_key"):
        mock_resp = httpx.Response(401, text="Unauthorized: Invalid API Key")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(RuntimeError) as exc_info:
                await client.search({"engine": "google_flights"})
            assert "Invalid SERPAPI_API_KEY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_error_quota_exhausted_429():
    client = SerpApiClient()
    with patch.object(settings, "SERPAPI_API_KEY", "dummy_key"):
        mock_resp = httpx.Response(429, text="Rate limit exceeded")
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(RuntimeError) as exc_info:
                await client.search({"engine": "google_flights"})
            assert "quota exceeded or rate limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_error_timeout():
    client = SerpApiClient()
    with patch.object(settings, "SERPAPI_API_KEY", "dummy_key"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Timed out")
            with pytest.raises(RuntimeError) as exc_info:
                await client.search({"engine": "google_flights"})
            assert "timed out" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_error_json_contains_error():
    client = SerpApiClient()
    with patch.object(settings, "SERPAPI_API_KEY", "dummy_key"):
        mock_resp = httpx.Response(200, json={"error": "Your account has run out of searches"})
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            with pytest.raises(RuntimeError) as exc_info:
                await client.search({"engine": "google_flights"})
            assert "quota exhausted" in str(exc_info.value).lower()
