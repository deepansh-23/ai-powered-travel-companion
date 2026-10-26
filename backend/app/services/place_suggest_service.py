"""Type-ahead suggestions for countries, states and cities (Geoapify autocomplete).

Used by the source/destination fields and by the "Did you mean...?" chips when a place
cannot be planned as typed. Results are cached for an hour to save API calls.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from app.services.usage_service import usage_recorder

from app.config import settings

logger = logging.getLogger(__name__)

AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"
_CACHE_TTL = 3600.0
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

_KIND_BY_RESULT_TYPE = {
    "country": "country",
    "state": "state",
    "city": "city",
    "county": "area",
    "locality": "area",
}
_KIND_LABEL = {"country": "Country", "state": "State / region", "city": "City", "area": "Area"}


def parse_autocomplete(data: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    """Geoapify response -> [{'label', 'name', 'kind', 'kind_label', 'country', 'state'}] (no duplicates)."""
    rows = data.get("results") if isinstance(data, dict) else None
    if rows is None and isinstance(data, dict):  # GeoJSON style
        rows = [f.get("properties", {}) for f in data.get("features", []) if isinstance(f, dict)]
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        kind = _KIND_BY_RESULT_TYPE.get(str(r.get("result_type") or "").lower())
        if not kind:
            continue
        country, state = r.get("country") or "", r.get("state") or ""
        if kind == "country":
            name = country or r.get("name") or ""
            label = name
        elif kind == "state":
            name = state or r.get("name") or ""
            label = ", ".join(x for x in (name, country) if x)
        else:
            name = r.get("city") or r.get("name") or r.get("county") or ""
            label = ", ".join(x for x in (name, state if state and state != name else "", country) if x)
        if not name or (kind, label.lower()) in seen:
            continue
        seen.add((kind, label.lower()))
        out.append({"label": label, "name": name, "kind": kind, "kind_label": _KIND_LABEL[kind],
                    "country": country, "state": state})
        if len(out) >= limit:
            break
    return out


class PlaceSuggestService:
    async def suggest(self, query: str, limit: int = 6) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Returns (suggestions, notice). Never raises: suggestions are a convenience, not a requirement."""
        q = (query or "").strip()
        if len(q) < 2:
            return [], None
        key = f"{q.lower()}|{limit}"
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return hit[1], None
        api_key = (settings.GEOAPIFY_API_KEY or "").strip().strip("'\"")
        if not api_key:
            return [], "Place suggestions need GEOAPIFY_API_KEY."
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                with usage_recorder.track("geoapify", "autocomplete") as _u:
                    resp = await client.get(AUTOCOMPLETE_URL, params={
                        "text": q, "format": "json", "limit": 10, "lang": "en", "apiKey": api_key})
                    _u.status = getattr(resp, "status_code", None)
            if resp.status_code != 200:
                return [], "Place suggestions are temporarily unavailable."
            items = parse_autocomplete(resp.json(), limit)
            _cache[key] = (time.time(), items)
            return items, None
        except Exception as exc:
            logger.info(f"Place suggestion lookup failed: {exc}")
            return [], "Place suggestions are temporarily unavailable."


place_suggest_service = PlaceSuggestService()
