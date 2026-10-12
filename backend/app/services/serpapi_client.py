"""SerpApi HTTP Client with short-term in-memory caching and strict error mapping (Section 6, 7A, 8).
Serves both Google Flights and Google Hotels using the single SERPAPI_API_KEY.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
CACHE_TTL_SECONDS = 900.0  # 15 minutes cache to conserve API credits


class SerpApiClient:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _get_api_key(self) -> str:
        key = getattr(settings, "SERPAPI_API_KEY", None)
        if not key or key.strip() in ("", "your_serpapi_api_key_here"):
            raise RuntimeError("Missing or unconfigured SERPAPI_API_KEY.")
        return key.strip()

    def _cache_key(self, params: Dict[str, Any]) -> str:
        # Create deterministic hash key ignoring the api_key itself
        filtered = {k: v for k, v in params.items() if k != "api_key"}
        serialized = json.dumps(filtered, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        cached = self._cache.get(cache_key)
        if cached:
            if time.time() - cached["timestamp"] < CACHE_TTL_SECONDS:
                return cached["data"]
            else:
                del self._cache[cache_key]
        return None

    def put_into_cache(self, cache_key: str, data: Dict[str, Any]):
        self._cache[cache_key] = {
            "timestamp": time.time(),
            "data": data
        }

    async def search(self, params: Dict[str, Any], timeout: float = 25.0) -> Dict[str, Any]:
        """Execute a SerpApi search query with caching and comprehensive error mapping."""
        api_key = self._get_api_key()

        full_params = dict(params)
        full_params["api_key"] = api_key

        cache_key = self._cache_key(full_params)
        cached_data = self.get_from_cache(cache_key)
        if cached_data is not None:
            logger.info(f"Returning cached SerpApi response for engine={params.get('engine')}")
            return cached_data

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(SERPAPI_BASE_URL, params=full_params)

                if response.status_code == 401 or response.status_code == 403:
                    raise RuntimeError("Invalid SERPAPI_API_KEY: authentication failed with SerpApi.")
                elif response.status_code == 429:
                    raise RuntimeError("SerpApi search quota exceeded or rate limit reached.")
                elif response.status_code >= 500:
                    raise RuntimeError(f"SerpApi provider service error (HTTP {response.status_code}).")

                try:
                    data = response.json()
                except Exception as exc:
                    raise RuntimeError(f"Malformed JSON response from SerpApi: {exc}")

                # Check if SerpApi returned an error inside JSON
                if "error" in data:
                    err_msg = str(data["error"]).lower()
                    if "api key" in err_msg or "unauthorized" in err_msg or "invalid" in err_msg:
                        raise RuntimeError(f"Invalid SERPAPI_API_KEY: {data['error']}")
                    elif "quota" in err_msg or "searches" in err_msg or "limit" in err_msg:
                        raise RuntimeError(f"SerpApi quota exhausted: {data['error']}")
                    else:
                        raise RuntimeError(f"SerpApi error: {data['error']}")

                self.put_into_cache(cache_key, data)
                return data

        except httpx.TimeoutException:
            raise RuntimeError("SerpApi request timed out.")
        except httpx.RequestError as exc:
            raise RuntimeError(f"Network connection to SerpApi failed: {str(exc)}")


serpapi_client = SerpApiClient()
