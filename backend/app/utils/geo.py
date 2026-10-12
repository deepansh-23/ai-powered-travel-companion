"""Geographic calculation and validation utilities.
Authoritative source for distance calculation (Haversine) and coordinate checks.
"""

import math
from typing import Optional, Tuple


EARTH_RADIUS_METERS = 6371000.0


def is_valid_coordinate(lat: Optional[float], lon: Optional[float]) -> bool:
    """Validate latitude and longitude ranges.
    Latitude must be between -90 and 90.
    Longitude must be between -180 and 180.
    """
    if lat is None or lon is None:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (ValueError, TypeError):
        return False

    if math.isnan(lat_f) or math.isnan(lon_f) or math.isinf(lat_f) or math.isinf(lon_f):
        return False

    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Calculate the great-circle distance between two points in meters using Haversine formula.
    Returns integer meters rounded to nearest whole meter.
    """
    if not (is_valid_coordinate(lat1, lon1) and is_valid_coordinate(lat2, lon2)):
        raise ValueError("Invalid coordinates provided to haversine_distance_m")

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = EARTH_RADIUS_METERS * c
    return int(round(distance))


def create_straight_line_geometry(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Generate a standard GeoJSON LineString geometry representing a straight line
    between origin and destination.
    Note GeoJSON format specifies [longitude, latitude].
    """
    return {
        "type": "LineString",
        "coordinates": [
            [round(lon1, 6), round(lat1, 6)],
            [round(lon2, 6), round(lat2, 6)]
        ]
    }
