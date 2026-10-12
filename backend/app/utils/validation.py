"""Authoritative validation utilities for places, ratings, websites, and names.
Enforces the critical data rules from Section 27 and Section 50.7.
"""

import re
from typing import Optional, Tuple, Set, Dict, Any
from urllib.parse import urlparse
import httpx

from app.config import settings
from app.utils.geo import is_valid_coordinate


# Website validation patterns
INVALID_NAME_PATTERNS = {
    "", "unnamed", "unnamed place", "unknown", "n/a", "na", "null", "none",
    "test", "test place", "placeholder", "undefined", "no name"
}

BLOCKED_HOSTNAMES = {
    "localhost", "127.0.0.1", "0.0.0.0", "example.com", "example.org",
    "example.net", "test.com", "invalid.example.org"
}

# Cache for verified websites to avoid repeated network checks: url -> (is_valid, timestamp)
_website_verification_cache: Dict[str, bool] = {}


def sanitize_place_name(name: Optional[str]) -> Optional[str]:
    """Validate and clean place name.
    Rejects None, empty, whitespace-only, or generic placeholder names.
    Returns cleaned name or None.
    """
    if not name or not isinstance(name, str):
        return None
    cleaned = name.strip()
    if not cleaned:
        return None
    if cleaned.lower() in INVALID_NAME_PATTERNS:
        return None
    if len(cleaned) < 2:
        return None
    return cleaned


def validate_website_url(url: Optional[str]) -> Optional[str]:
    """Validate and normalize website URL strictly according to Section 50.7.
    - Accepts only absolute http/https URLs.
    - Normalizes bare domains starting with www. to https://
    - Rejects javascript:, data:, file:, localhost, placeholder domains (example.com).
    - Returns normalized absolute URL string or None.
    """
    if not url or not isinstance(url, str):
        return None
    trimmed = url.strip()
    if not trimmed:
        return None

    # Check for dangerous schemes
    lower = trimmed.lower()
    if lower.startswith(("javascript:", "data:", "file:", "vbscript:", "about:")):
        return None

    # Auto-prefix standard web URLs if bare domain
    if trimmed.startswith("www."):
        trimmed = "https://" + trimmed

    # Ensure has scheme
    if not (trimmed.startswith("http://") or trimmed.startswith("https://")):
        return None

    try:
        parsed = urlparse(trimmed)
    except Exception:
        return None

    if not parsed.scheme or parsed.scheme.lower() not in ("http", "https"):
        return None

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return None

    # Reject localhost, IPs, and placeholder domains
    if hostname in BLOCKED_HOSTNAMES:
        return None
    if hostname.endswith(".example.com") or hostname.endswith(".example.org"):
        return None

    # Must have at least one dot in hostname unless it's a valid TLD
    if "." not in hostname:
        return None

    return trimmed


async def is_website_reachable(url: str, timeout: float = 3.0) -> bool:
    """Optional live reachability check controlled by VERIFY_WEBSITES.
    Sends lightweight HEAD request (falls back to GET).
    Follows redirects. Treats 2xx, 3xx, 401, 403, 405, 429 as reachable.
    Treats DNS errors, connection timeouts, 404, 5xx as unreachable.
    """
    if url in _website_verification_cache:
        return _website_verification_cache[url]

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            headers = {"User-Agent": "SmartLocalGuideBot/1.0 (+https://smartlocalguide.example)"}
            try:
                resp = await client.head(url, headers=headers)
            except (httpx.RequestError, httpx.UnsupportedProtocol):
                resp = await client.get(url, headers=headers)

            # Per Section 50.7: treat 2xx, 3xx, 401, 403, 405, 429 as reachable
            # treat 404, 410, 5xx as unreachable
            reachable = resp.status_code in (
                200, 201, 202, 203, 204, 301, 302, 303, 307, 308,
                401, 403, 405, 429
            )
            _website_verification_cache[url] = reachable
            return reachable
    except Exception:
        _website_verification_cache[url] = False
        return False


def validate_rating(
    rating: Optional[float],
    rating_source: Optional[str],
    rating_count: Optional[int] = None
) -> Tuple[Optional[float], Optional[str], Optional[int]]:
    """Validate rating strictly according to Section 27 and 50.7:
    - Rating must be a number between 0.0 and 5.0.
    - Rating MUST have an accompanying non-empty rating_source.
    - If either is missing or invalid, all rating fields must be None.
    - Never default a missing rating to 0.
    """
    if rating is None or rating_source is None:
        return None, None, None

    try:
        rating_f = round(float(rating), 1)
    except (ValueError, TypeError):
        return None, None, None

    if rating_f < 0.0 or rating_f > 5.0:
        return None, None, None

    source_clean = str(rating_source).strip()
    if not source_clean:
        return None, None, None

    clean_count = None
    if rating_count is not None:
        try:
            cnt = int(rating_count)
            if cnt >= 0:
                clean_count = cnt
        except (ValueError, TypeError):
            clean_count = None

    return rating_f, source_clean, clean_count


def deduplicate_places(places: list) -> list:
    """Deduplicate places based on normalized name and address or coordinates.
    Preserves the first occurrence.
    """
    seen: Set[str] = set()
    unique = []

    for place in places:
        # Check if place is a dict or model
        name = place.get("name") if isinstance(place, dict) else getattr(place, "name", None)
        address = place.get("address") if isinstance(place, dict) else getattr(place, "address", None)
        lat = place.get("latitude") if isinstance(place, dict) else getattr(place, "latitude", None)
        lon = place.get("longitude") if isinstance(place, dict) else getattr(place, "longitude", None)

        sanitized_name = sanitize_place_name(name)
        if not sanitized_name:
            continue

        key = sanitized_name.lower()
        if address:
            key += f"|{str(address).strip().lower()}"
        elif is_valid_coordinate(lat, lon):
            key += f"|{round(float(lat), 3)},{round(float(lon), 3)}"

        if key in seen:
            continue
        seen.add(key)
        unique.append(place)

    return unique
