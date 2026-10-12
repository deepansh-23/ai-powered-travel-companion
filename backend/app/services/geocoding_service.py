"""Geocoding Service — converts location names into geographic coordinates (lat/lon).

Uses Geoapify Forward Geocoding API when MOCK_MODE=false.
Uses local locations.json when MOCK_MODE=true.
Never silently falls back to arbitrary cities in live mode.
"""

from typing import Optional, Dict, Any, List
import json
import urllib.parse
import httpx

from app.config import settings
from app.models.places import Center


class GeocodingService:
    def __init__(self):
        self._mock_locations: Optional[List[Dict[str, Any]]] = None

    def _load_mock_locations(self) -> List[Dict[str, Any]]:
        if self._mock_locations is None:
            path = settings.DATA_MOCK_DIR / "locations.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    self._mock_locations = json.load(f).get("locations", [])
            else:
                self._mock_locations = []
        return self._mock_locations

    def resolve_center(
        self,
        location: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Center:
        """Resolve either explicit coordinates or a location name string into a Center object.
        
        Raises:
            ValueError: If location is empty or not found.
            RuntimeError: If live geocoding service encounters an API or network error.
        """
        # 1. Direct coordinates take precedence
        if latitude is not None and longitude is not None:
            if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
                raise ValueError(
                    f"Coordinates out of range: latitude={latitude}, longitude={longitude}"
                )
            label = location.strip() if (location and location.strip()) else f"{latitude:.4f}, {longitude:.4f}"
            return Center(
                latitude=float(latitude),
                longitude=float(longitude),
                label=label,
                kind="user_location",
            )

        # 2. Location string validation
        if not location or not location.strip():
            raise ValueError("Location string cannot be empty.")

        clean_location = location.strip()

        # 3. Mock mode lookup
        if settings.MOCK_MODE:
            return self._resolve_mock(clean_location)

        # 4. Live Geoapify Forward Geocoding
        return self._resolve_live_geoapify(clean_location)

    def _resolve_mock(self, location: str) -> Center:
        """Look up location in bundled mock locations.json."""
        locations = self._load_mock_locations()
        query = location.lower().strip()

        # Exact or alias match
        for loc in locations:
            name = loc.get("name", "").lower()
            aliases = [a.lower() for a in loc.get("aliases", [])]
            if query == name or query in aliases or any(query in a or a in query for a in aliases):
                return Center(
                    latitude=loc["latitude"],
                    longitude=loc["longitude"],
                    label=loc.get("label", loc["name"]),
                    kind="search_area",
                )

        # In mock mode, if not in locations.json, fail explicitly so test suite
        # and mock consumer know this location has no sample dataset.
        raise ValueError(
            f"Could not find location '{location}'. In mock mode, only sample "
            "locations are available (Delhi, London, Manchester, Edinburgh, New York, Paris, Tokyo)."
        )

    def _resolve_live_geoapify(self, location: str) -> Center:
        """Call Geoapify Forward Geocoding API with safely URL-encoded text and clean key."""
        api_key = (settings.GEOAPIFY_API_KEY or "").strip().strip("'\"")
        if not api_key:
            raise RuntimeError(
                "Location service is not configured. (Missing GEOAPIFY_API_KEY)"
            )

        encoded_text = urllib.parse.quote(location)
        url = "https://api.geoapify.com/v1/geocode/search"
        params = {
            "text": location,
            "apiKey": api_key,
        }

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 400:
                    raise RuntimeError(
                        f"Location service error (400). Please check your query or API key."
                    )
                elif resp.status_code in (401, 403):
                    raise RuntimeError(
                        "Location service authorization error (401/403). Please verify your GEOAPIFY_API_KEY in .env."
                    )
                elif resp.status_code != 200:
                    raise RuntimeError(
                        f"Location service error ({resp.status_code}). Please try again."
                    )

                data = resp.json()
        except httpx.TimeoutException:
            raise RuntimeError("Location service timed out. Please try again.")
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach location service ({exc}). Please try again.")

        features = data.get("features", [])
        if not features:
            raise ValueError(f"Could not find location '{location}'. Please check the spelling.")

        first = features[0]
        geometry = first.get("geometry", {})
        coords = geometry.get("coordinates", [])

        if len(coords) < 2:
            raise ValueError(f"Could not resolve coordinates for '{location}'.")

        # GeoJSON is [longitude, latitude]
        lon = float(coords[0])
        lat = float(coords[1])

        props = first.get("properties", {})
        label = (
            props.get("formatted")
            or props.get("city")
            or props.get("name")
            or location.title()
        )

        return Center(
            latitude=lat,
            longitude=lon,
            label=label,
            kind="search_area",
        )


geocoding_service = GeocodingService()