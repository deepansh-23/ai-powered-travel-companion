"""Routing service implementing Section 50.7 requirements:
- Keyless public OSRM service through backend
- Request validation (max 50 km distance)
- In-memory cache per origin/destination/mode
- 5-second timeout with graceful straight-line fallback (is_approximate: true)
"""

import logging
from typing import Dict, Any, Optional
import httpx

from app.config import settings
from app.utils.geo import (
    is_valid_coordinate,
    haversine_distance_m,
    create_straight_line_geometry
)
from app.utils.helpers import mask_coordinates_for_logs
from app.models.route import RouteResponse

logger = logging.getLogger(__name__)

# In-memory LRU-like route cache: cache_key -> RouteResponse
_route_cache: Dict[str, RouteResponse] = {}
MAX_ALLOWED_DISTANCE_KM = 50.0


class RoutingService:
    def __init__(self):
        self.base_url = settings.ROUTING_BASE_URL.rstrip("/")
        self.timeout = settings.ROUTING_TIMEOUT_SECONDS

    def _get_cache_key(self, lat1: float, lon1: float, lat2: float, lon2: float, mode: str) -> str:
        return f"{round(lat1, 4)},{round(lon1, 4)}->{round(lat2, 4)},{round(lon2, 4)}:{mode}"

    def _create_fallback_route(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        mode: str,
        reason: str
    ) -> RouteResponse:
        """Create a straight-line fallback route clearly flagged as approximate."""
        distance_m = haversine_distance_m(lat1, lon1, lat2, lon2)
        geometry = create_straight_line_geometry(lat1, lon1, lat2, lon2)

        if distance_m < 1000:
            dist_str = f"{distance_m} m"
        else:
            dist_str = f"{round(distance_m / 1000.0, 1)} km"

        summary = f"Approximate straight-line distance: {dist_str} (Route unavailable)"
        return RouteResponse(
            geometry=geometry,
            distance_m=distance_m,
            duration_s=None,
            mode=mode,
            provider="fallback-haversine",
            is_approximate=True,
            summary=summary
        )

    async def get_route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        mode: str = "walking"
    ) -> RouteResponse:
        """Fetch route geometry and navigation details from routing provider,
        or gracefully fall back to straight line with is_approximate: true.
        """
        if not (is_valid_coordinate(origin_lat, origin_lon) and is_valid_coordinate(dest_lat, dest_lon)):
            raise ValueError("Invalid coordinates supplied for routing")

        # Check maximum separation
        straight_dist_m = haversine_distance_m(origin_lat, origin_lon, dest_lat, dest_lon)
        if straight_dist_m > MAX_ALLOWED_DISTANCE_KM * 1000.0:
            raise ValueError(
                f"Origin and destination exceed maximum route limit of {int(MAX_ALLOWED_DISTANCE_KM)} km"
            )

        cache_key = self._get_cache_key(origin_lat, origin_lon, dest_lat, dest_lon, mode)
        if cache_key in _route_cache:
            return _route_cache[cache_key]

        # Mode mapping for OSRM profiles
        # OSRM public demo server typically supports foot/walking and driving
        profile = "foot" if mode == "walking" else "driving"
        # OSRM URL format: {base_url}/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson
        osrm_url = (
            f"{self.base_url}/route/v1/{profile}/"
            f"{origin_lon:.6f},{origin_lat:.6f};{dest_lon:.6f},{dest_lat:.6f}"
            "?overview=full&geometries=geojson"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(osrm_url)

                if response.status_code == 200:
                    data = response.json()
                    routes = data.get("routes", [])
                    if routes:
                        primary_route = routes[0]
                        geometry = primary_route.get("geometry", {})
                        distance_m = int(round(primary_route.get("distance", straight_dist_m)))
                        duration_s = int(round(primary_route.get("duration", 0)))

                        # Format user-friendly summary
                        dist_text = f"{distance_m} m" if distance_m < 1000 else f"{round(distance_m / 1000.0, 1)} km"
                        mins = max(1, int(round(duration_s / 60.0)))
                        summary = f"{mode.title()} · {dist_text} · {mins} min"

                        route_resp = RouteResponse(
                            geometry=geometry,
                            distance_m=distance_m,
                            duration_s=duration_s,
                            mode=mode,
                            provider="osrm-public",
                            is_approximate=False,
                            summary=summary
                        )
                        # Cache successful result
                        if len(_route_cache) > 200:
                            _route_cache.clear()
                        _route_cache[cache_key] = route_resp
                        return route_resp

        except Exception as exc:
            # Privacy-safe logging (Section 42 & 50.7): round user coordinates in logs
            logger.warning(
                "Routing provider failed (%s) from %s to %s. Falling back to straight line.",
                type(exc).__name__,
                mask_coordinates_for_logs(origin_lat, origin_lon),
                mask_coordinates_for_logs(dest_lat, dest_lon)
            )

        # Fallback to straight line
        fallback = self._create_fallback_route(
            origin_lat, origin_lon, dest_lat, dest_lon, mode, "routing_unavailable"
        )
        return fallback


routing_service = RoutingService()
