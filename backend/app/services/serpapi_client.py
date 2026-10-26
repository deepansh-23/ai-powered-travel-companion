"""SerpApi HTTP Client with short-term in-memory caching and strict error mapping (Section 6, 7A, 8).
Serves both Google Flights and Google Hotels. Uses SERPAPI_API_KEY, and when that key is out of searches (or
rejected) switches by itself to the backup key SERP_API_KEY2, so a used-up key does not break the site.
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from app.services.usage_service import usage_recorder

from app.config import settings

logger = logging.getLogger(__name__)

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
CACHE_TTL_SECONDS = 900.0  # 15 minutes cache to conserve API credits

# Settings that hold SerpApi keys, in order of preference (first = main key, second = backup key).
KEY_SETTINGS = ("SERPAPI_API_KEY", "SERP_API_KEY2")
_PLACEHOLDERS = ("", "your_serpapi_api_key_here", "your_serpapi_api_key2_here")
# After a key is reported out of searches / invalid, skip it for a while instead of wasting a call on every search.
QUOTA_COOLDOWN_SECONDS = 3600.0
RATE_COOLDOWN_SECONDS = 600.0


class SerpApiKeyProblem(RuntimeError):
    """The KEY (not the request) is the problem: out of searches, rate limited or rejected. Worth trying the backup key."""

    def __init__(self, message: str, cooldown: float):
        super().__init__(message)
        self.cooldown = cooldown


class SerpApiClient:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._resting_until: Dict[str, float] = {}   # key fingerprint -> time before which it is skipped

    def _configured_keys(self) -> List[str]:
        """Usable keys in order of preference (main first, backup second). Placeholders and duplicates are ignored."""
        keys: List[str] = []
        for name in KEY_SETTINGS:
            value = (getattr(settings, name, None) or "").strip()
            if value and value not in _PLACEHOLDERS and value not in keys:
                keys.append(value)
        if not keys:
            raise RuntimeError("Missing or unconfigured SERPAPI_API_KEY.")
        return keys

    def _get_api_key(self) -> str:
        return self._configured_keys()[0]

    @staticmethod
    def _key_id(key: str) -> str:
        """A short fingerprint, so a key can be tracked without ever storing or logging the key itself."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _keys_to_try(self) -> List[str]:
        """Keys not resting after a failure, in order. If every key is resting, try them all again."""
        keys = self._configured_keys()
        now = time.time()
        ready = [k for k in keys if self._resting_until.get(self._key_id(k), 0.0) <= now]
        return ready or keys

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
        """Execute a SerpApi search query with caching, comprehensive error mapping and backup-key switching."""
        keys = self._keys_to_try()

        cache_key = self._cache_key(params)          # the key is not part of it: results are shared between keys
        cached_data = self.get_from_cache(cache_key)
        if cached_data is not None:
            logger.info(f"Returning cached SerpApi response for engine={params.get('engine')}")
            return cached_data

        last_problem: Optional[SerpApiKeyProblem] = None
        for slot, api_key in enumerate(keys, start=1):
            try:
                return await self._search_with_key(api_key, params, timeout, cache_key, slot)
            except SerpApiKeyProblem as exc:
                last_problem = exc
                self._resting_until[self._key_id(api_key)] = time.time() + exc.cooldown
                if slot < len(keys):
                    logger.warning("SerpApi key #%d is out of searches or was rejected (%s); switching to the backup key.", slot, exc)
                else:
                    logger.error("SerpApi: every configured key is out of searches or was rejected (%s).", exc)
        raise last_problem  # all keys failed: same RuntimeError text as before, so callers behave as they always did

    async def _search_with_key(self, api_key: str, params: Dict[str, Any], timeout: float, cache_key: str, slot: int) -> Dict[str, Any]:
        full_params = dict(params)
        full_params["api_key"] = api_key
        label = str(params.get("engine") or "search") + (f" (key {slot})" if slot > 1 else "")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                with usage_recorder.track("serpapi", label) as _u:
                    response = await client.get(SERPAPI_BASE_URL, params=full_params)
                    _u.status = getattr(response, "status_code", None)

                if response.status_code == 401 or response.status_code == 403:
                    raise SerpApiKeyProblem("Invalid SERPAPI_API_KEY: authentication failed with SerpApi.", QUOTA_COOLDOWN_SECONDS)
                elif response.status_code == 429:
                    raise SerpApiKeyProblem("SerpApi search quota exceeded or rate limit reached.", RATE_COOLDOWN_SECONDS)
                elif response.status_code >= 500:
                    raise RuntimeError(f"SerpApi provider service error (HTTP {response.status_code}).")

                try:
                    data = response.json()
                except Exception as exc:
                    raise RuntimeError(f"Malformed JSON response from SerpApi: {exc}")

                # Check if SerpApi returned an error inside JSON
                if "error" in data:
                    err_msg = str(data["error"]).lower()
                    if "api key" in err_msg or "unauthorized" in err_msg:
                        raise SerpApiKeyProblem(f"Invalid SERPAPI_API_KEY: {data['error']}", QUOTA_COOLDOWN_SECONDS)
                    elif "invalid" in err_msg:
                        raise RuntimeError(f"Invalid SERPAPI_API_KEY: {data['error']}")   # a bad request, not a key problem
                    elif "quota" in err_msg or "searches" in err_msg or "limit" in err_msg:
                        raise SerpApiKeyProblem(f"SerpApi quota exhausted: {data['error']}", QUOTA_COOLDOWN_SECONDS)
                    else:
                        raise RuntimeError(f"SerpApi error: {data['error']}")

                self.put_into_cache(cache_key, data)
                return data

        except httpx.TimeoutException:
            raise RuntimeError("SerpApi request timed out.")
        except httpx.RequestError as exc:
            raise RuntimeError(f"Network connection to SerpApi failed: {str(exc)}")


serpapi_client = SerpApiClient()
