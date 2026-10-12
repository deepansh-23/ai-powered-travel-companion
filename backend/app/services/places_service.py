"""Places, Cafes, and Medical Service layer — dual-mode.

MOCK_MODE=true  → loads from bundled mock JSON files (no API calls).
MOCK_MODE=false → fetches real data from Geoapify Places API.

Enforces all validation rules:
- Unnamed place rejection
- Place deduplication
- Website URL validation
- Rating validation
- Backend Haversine distance calculation
- Nearest-first sorting
- Radius enforcement on every query
"""

import json
import httpx
from typing import List, Dict, Any, Optional, Set

from app.config import settings
from app.models.places import Center, Place, PlacesSearchResponse
from app.models.cafes import Cafe, CafesSearchResponse
from app.models.medical import MedicalFacility, MedicalSearchResponse
from app.utils.geo import is_valid_coordinate, haversine_distance_m
from app.utils.validation import (
    sanitize_place_name,
    validate_website_url,
    validate_rating,
    deduplicate_places,
    is_website_reachable,
)
from app.utils.helpers import synthesize_fallback_description

# ---------------------------------------------------------------------------
# Geoapify Places API constants
# ---------------------------------------------------------------------------
_GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"

# Geoapify category sets for each feature (strictly valid Geoapify syntax)
_PLACES_CATEGORIES = (
    "tourism.attraction,tourism.sights,entertainment.museum,entertainment.culture,"
    "commercial.shopping_mall,catering.restaurant,accommodation.hotel,leisure.park"
)
_CAFE_CATEGORIES = "catering.cafe"
_MEDICAL_CATEGORIES = (
    "healthcare.hospital,healthcare.pharmacy,healthcare.clinic_or_praxis"
)

# Map Geoapify category strings → our internal labels
_SERVICE_TYPE_MAP = {
    "healthcare.hospital": "24/7 hospitals",
    "healthcare.emergency": "Emergency departments",
    "healthcare.urgent_care": "Urgent care",
    "healthcare.clinic_or_praxis": "Clinics",
    "healthcare.pharmacy": "Late-night pharmacies",
}
_CATEGORY_MAP = {
    "tourism.attraction": "attraction",
    "tourism.sights": "attraction",
    "entertainment.museum": "museum",
    "tourism.museum": "museum",
    "entertainment.culture": "attraction",
    "commercial.shopping_mall": "shopping",
    "commercial.shopping": "shopping",
    "catering.restaurant": "restaurant",
    "catering.cafe": "cafe",
    "catering.coffee_shop": "cafe",
    "catering.tea_house": "cafe",
    "accommodation.hotel": "hotel",
    "leisure.park": "park",
    "natural.park": "park",
}


# ---------------------------------------------------------------------------
# Geoapify fetcher
import logging

logger = logging.getLogger(__name__)


def _fetch_geoapify_places(
    lat: float,
    lon: float,
    radius_m: int,
    categories: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Call Geoapify Places API and return raw feature list."""
    api_key = (settings.GEOAPIFY_API_KEY or "").strip().strip("'\"")
    if not api_key:
        raise RuntimeError(
            "Location service is not configured. (Missing GEOAPIFY_API_KEY)"
        )

    # Validate categories string follows comma-separated format
    clean_categories = ",".join(
        c.strip() for c in categories.split(",") if c.strip()
    )

    params = {
        "categories": clean_categories,
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": limit,
        "apiKey": api_key,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(_GEOAPIFY_PLACES_URL, params=params)
            if resp.status_code == 400:
                # Previously this silently returned an empty list here, which
                # made every live search look like "no places found" with no
                # indication a request was actually malformed (e.g. an
                # invalid category string) — surface it as a real, visible
                # error instead, same as the 401/403 case below, so the
                # actual Geoapify error detail reaches the user/logs.
                logger.warning(
                    f"Geoapify Places API returned 400 for categories='{clean_categories}'. "
                    f"Detail: {resp.text}"
                )
                raise RuntimeError(
                    f"Location service rejected this request (invalid search "
                    f"parameters). Detail: {resp.text}"
                )
            if resp.status_code in (401, 403):
                raise RuntimeError(
                    "Invalid GEOAPIFY_API_KEY. Please verify your API key in .env."
                )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise RuntimeError(
            "Unable to retrieve live location data right now. Please try again."
        )
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Location service error ({exc.response.status_code}). Please try again."
        )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Unable to retrieve live location data. Please try again. ({exc})"
        )

    return data.get("features", [])


def _geoapify_feature_to_dict(feat: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a Geoapify GeoJSON feature into our internal place dict."""
    props = feat.get("properties", {})
    geometry = feat.get("geometry", {})
    coords = geometry.get("coordinates", [])

    lon = coords[0] if len(coords) > 1 else None
    lat = coords[1] if len(coords) > 1 else None

    # Name — use the best available name field
    name = (
        props.get("name")
        or props.get("name_international", {}).get("en")
        or props.get("address_line1")
        or ""
    ).strip()

    # Category mapping
    raw_categories = props.get("categories", [])
    internal_cat = "general"
    for rc in raw_categories:
        for prefix, mapped in _CATEGORY_MAP.items():
            if rc.startswith(prefix):
                internal_cat = mapped
                break
        if internal_cat != "general":
            break

    # Address
    address = props.get("address_line2") or props.get("formatted") or None

    # Place ID
    place_id = props.get("place_id") or props.get("osm_id") or None

    return {
        "id": str(place_id) if place_id else None,
        "name": name,
        "category": internal_cat,
        "description": None,
        "description_source": "geoapify",
        "address": address,
        "latitude": lat,
        "longitude": lon,
        "rating": None,
        "rating_count": None,
        "rating_source": None,
        "website": props.get("website"),
        "phone": props.get("contact", {}).get("phone") if isinstance(props.get("contact"), dict) else props.get("phone"),
        "source": "geoapify-live",
        # Extra for medical
        "service_type": None,
        "is_24_7": None,
        "opening_hours": props.get("opening_hours"),
        "raw_categories": raw_categories,
    }


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class PlacesService:
    def __init__(self):
        self._places_cache: Optional[List[Dict[str, Any]]] = None
        self._cafes_cache: Optional[List[Dict[str, Any]]] = None
        self._medical_cache: Optional[List[Dict[str, Any]]] = None

    # -----------------------------------------------------------------------
    # Mock data loaders
    # -----------------------------------------------------------------------

    def _load_mock(self, filename: str) -> List[Dict[str, Any]]:
        path = settings.DATA_MOCK_DIR / filename
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key in ("places", "cafes", "medical"):
                    if key in data:
                        return data[key]
        return []

    # -----------------------------------------------------------------------
    # Validation / enrichment pipeline (shared by mock + live)
    # -----------------------------------------------------------------------

    async def _process_place_dict(
        self,
        raw: Dict[str, Any],
        center: Center,
    ) -> Optional[Dict[str, Any]]:
        """Validate and enrich a single raw place dictionary."""
        # 1. Name validation — reject unnamed/generic names
        name = sanitize_place_name(raw.get("name"))
        if not name:
            return None

        # 2. Coordinates validation
        lat = raw.get("latitude")
        lon = raw.get("longitude")
        has_coords = is_valid_coordinate(lat, lon)

        clean_lat = float(lat) if has_coords else None
        clean_lon = float(lon) if has_coords else None

        # 3. Distance calculation (Haversine from center)
        distance_m = None
        if has_coords:
            distance_m = haversine_distance_m(
                center.latitude, center.longitude, clean_lat, clean_lon
            )

        # 4. Rating validation
        clean_rating, clean_source, clean_count = validate_rating(
            raw.get("rating"),
            raw.get("rating_source"),
            raw.get("rating_count"),
        )

        # 5. Website validation
        website = validate_website_url(raw.get("website"))
        if website and settings.VERIFY_WEBSITES:
            reachable = await is_website_reachable(
                website,
                timeout=settings.WEBSITE_CHECK_TIMEOUT_SECONDS,
            )
            if not reachable:
                website = None

        # 6. Phone validation
        phone = raw.get("phone")
        clean_phone = str(phone).strip() if (phone and str(phone).strip()) else None

        # 7. Description — generate neutral template if missing/too short
        desc = raw.get("description")
        desc_src = raw.get("description_source", "provider")
        if not desc or len(str(desc).strip()) < 10:
            desc = synthesize_fallback_description(
                name,
                raw.get("category", "place"),
                raw.get("address"),
            )
            desc_src = "generated_template"

        return {
            "id": raw.get("id") or f"place-{abs(hash(name)) % 100000}",
            "name": name,
            "category": (raw.get("category") or "general").lower(),
            "description": str(desc).strip(),
            "description_source": desc_src,
            "address": raw.get("address"),
            "latitude": clean_lat,
            "longitude": clean_lon,
            "distance_m": distance_m,
            "rating": clean_rating,
            "rating_count": clean_count,
            "rating_source": clean_source,
            "website": website,
            "phone": clean_phone,
            "source": raw.get("source", "unknown"),
        }

    # -----------------------------------------------------------------------
    # Deduplication helper (by place_id OR normalised name+coords)
    # -----------------------------------------------------------------------

    @staticmethod
    def _dedup_live(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Set[str] = set()
        out: List[Dict[str, Any]] = []
        for item in items:
            pid = item.get("id")
            name = (item.get("name") or "").strip().lower()
            lat = round(float(item["latitude"]), 4) if item.get("latitude") is not None else None
            lon = round(float(item["longitude"]), 4) if item.get("longitude") is not None else None
            key = pid or f"{name}|{lat}|{lon}"
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    # -----------------------------------------------------------------------
    # Public: search_places
    # -----------------------------------------------------------------------

    async def search_places(
        self,
        center: Center,
        categories: Optional[List[str]] = None,
        radius_km: float = 3.0,
        limit: int = 30,
    ) -> PlacesSearchResponse:
        radius_m = int(radius_km * 1000)

        if settings.MOCK_MODE:
            # Load mock data (Delhi sample set)
            if self._places_cache is None:
                self._places_cache = self._load_mock("places.json")
            raw_list = deduplicate_places(self._places_cache)
        else:
            # Live Geoapify fetch
            features = _fetch_geoapify_places(
                center.latitude, center.longitude,
                radius_m, _PLACES_CATEGORIES, limit=50,
            )
            raw_list = self._dedup_live(
                [_geoapify_feature_to_dict(f) for f in features]
            )

        processed: List[Place] = []
        counts_by_cat: Dict[str, int] = {}
        max_dist_m = float(radius_m)

        for item in raw_list:
            clean_item = await self._process_place_dict(item, center)
            if not clean_item:
                continue

            cat = clean_item["category"]
            dist = clean_item.get("distance_m")

            # Radius filter (skip places outside radius that have coords)
            if dist is not None and dist > max_dist_m:
                continue

            counts_by_cat[cat] = counts_by_cat.get(cat, 0) + 1

            # Category filter
            if categories and "all" not in [c.lower() for c in categories]:
                if cat not in [c.lower() for c in categories]:
                    continue

            processed.append(Place(**clean_item))

        processed.sort(key=lambda p: (p.distance_m is None, p.distance_m or 0, p.name))
        final_list = processed[:limit]

        return PlacesSearchResponse(
            center=center,
            radius_km=radius_km,
            total=len(final_list),
            counts_by_category=counts_by_cat,
            data_mode="mock" if settings.MOCK_MODE else "live",
            places=final_list,
        )

    # -----------------------------------------------------------------------
    # Public: search_cafes
    # -----------------------------------------------------------------------

    async def search_cafes(
        self,
        center: Center,
        amenities: Optional[List[str]] = None,
        radius_km: float = 3.0,
        limit: int = 30,
    ) -> CafesSearchResponse:
        radius_m = int(radius_km * 1000)

        if settings.MOCK_MODE:
            if self._cafes_cache is None:
                self._cafes_cache = self._load_mock("cafes.json")
            raw_list = deduplicate_places(self._cafes_cache)
        else:
            features = _fetch_geoapify_places(
                center.latitude, center.longitude,
                radius_m, _CAFE_CATEGORIES, limit=50,
            )
            raw_list = self._dedup_live(
                [_geoapify_feature_to_dict(f) for f in features]
            )
            # Tag as cafe
            for item in raw_list:
                item["category"] = "cafe"

        processed: List[Cafe] = []
        counts_by_amenity: Dict[str, int] = {}
        max_dist_m = float(radius_m)

        for item in raw_list:
            clean_item = await self._process_place_dict(item, center)
            if not clean_item:
                continue

            dist = clean_item.get("distance_m")
            if dist is not None and dist > max_dist_m:
                continue

            item_amenities = item.get("amenities", [])
            for am in item_amenities:
                counts_by_amenity[am] = counts_by_amenity.get(am, 0) + 1

            if amenities and "all" not in [a.lower() for a in amenities]:
                requested = [a.lower() for a in amenities]
                if not all(req in [a.lower() for a in item_amenities] for req in requested):
                    continue

            clean_item["amenities"] = item_amenities
            processed.append(Cafe(**clean_item))

        processed.sort(key=lambda c: (c.distance_m is None, c.distance_m or 0, c.name))
        final_list = processed[:limit]

        return CafesSearchResponse(
            center=center,
            radius_km=radius_km,
            total=len(final_list),
            counts_by_amenity=counts_by_amenity,
            data_mode="mock" if settings.MOCK_MODE else "live",
            cafes=final_list,
        )

    # -----------------------------------------------------------------------
    # Public: search_medical
    # -----------------------------------------------------------------------

    async def search_medical(
        self,
        center: Center,
        service_types: Optional[List[str]] = None,
        radius_km: float = 5.0,
        limit: int = 30,
    ) -> MedicalSearchResponse:
        radius_m = int(radius_km * 1000)

        if settings.MOCK_MODE:
            if self._medical_cache is None:
                self._medical_cache = self._load_mock("medical.json")
            raw_list = deduplicate_places(self._medical_cache)
        else:
            features = _fetch_geoapify_places(
                center.latitude, center.longitude,
                radius_m, _MEDICAL_CATEGORIES, limit=50,
            )
            raw_list_raw = [_geoapify_feature_to_dict(f) for f in features]
            # Assign service_type from raw Geoapify categories
            for item in raw_list_raw:
                raw_cats = item.get("raw_categories", [])
                assigned = "Clinics"
                for rc in raw_cats:
                    for prefix, stype in _SERVICE_TYPE_MAP.items():
                        if rc.startswith(prefix):
                            assigned = stype
                            break
                    if assigned != "Clinics":
                        break
                item["service_type"] = assigned
                item["category"] = assigned.lower()
                # Opening hours hint for 24/7 — only mark when we have evidence
                oh = item.get("opening_hours") or ""
                if "24/7" in oh or "00:00-24:00" in oh:
                    item["is_24_7"] = True
                else:
                    item["is_24_7"] = None  # unverified
            raw_list = self._dedup_live(raw_list_raw)

        processed: List[MedicalFacility] = []
        counts_by_service: Dict[str, int] = {}
        max_dist_m = float(radius_m)

        for item in raw_list:
            clean_item = await self._process_place_dict(item, center)
            if not clean_item:
                continue

            service_type = item.get("service_type") or clean_item.get("category", "Clinics")
            dist = clean_item.get("distance_m")

            if dist is not None and dist > max_dist_m:
                continue

            counts_by_service[service_type] = counts_by_service.get(service_type, 0) + 1

            if service_types and "all" not in [s.lower() for s in service_types]:
                if service_type.lower() not in [s.lower() for s in service_types]:
                    continue

            is_24_7 = item.get("is_24_7")
            clean_item["service_type"] = service_type
            clean_item["is_24_7"] = bool(is_24_7) if is_24_7 is not None else None

            processed.append(MedicalFacility(**clean_item))

        processed.sort(key=lambda m: (m.distance_m is None, m.distance_m or 0, m.name))
        final_list = processed[:limit]

        return MedicalSearchResponse(
            center=center,
            radius_km=radius_km,
            total=len(final_list),
            counts_by_service_type=counts_by_service,
            emergency_disclaimer=(
                "In case of a life-threatening medical emergency, immediately call "
                "local emergency services (112 in India, 999 in the UK, 911 in the US). "
                "Do not rely solely on this guide for emergency triage."
            ),
            data_mode="mock" if settings.MOCK_MODE else "live",
            medical=final_list,
        )


places_service = PlacesService()