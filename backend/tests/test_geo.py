"""Tests for geographic calculations and coordinates (Section 50.7 & Section 43).
"""

import pytest
from app.utils.geo import (
    is_valid_coordinate,
    haversine_distance_m,
    create_straight_line_geometry
)


def test_is_valid_coordinate():
    # Valid
    assert is_valid_coordinate(53.4808, -2.2426) is True
    assert is_valid_coordinate(0.0, 0.0) is True
    assert is_valid_coordinate(-90.0, 180.0) is True
    assert is_valid_coordinate(90.0, -180.0) is True

    # Invalid ranges
    assert is_valid_coordinate(91.0, 0.0) is False
    assert is_valid_coordinate(-90.1, 0.0) is False
    assert is_valid_coordinate(0.0, 180.5) is False
    assert is_valid_coordinate(0.0, -181.0) is False

    # Invalid types
    assert is_valid_coordinate(None, -2.0) is False
    assert is_valid_coordinate(53.0, None) is False
    assert is_valid_coordinate("invalid", -2.0) is False


def test_haversine_distance_m():
    # India Gate (28.6129, 77.2295) to National Museum (28.6117, 77.2194)
    # Approx 950-1050 meters
    dist = haversine_distance_m(28.6129, 77.2295, 28.6117, 77.2194)
    assert 950 <= dist <= 1050

    # Same location
    assert haversine_distance_m(28.6315, 77.2167, 28.6315, 77.2167) == 0


def test_create_straight_line_geometry():
    geom = create_straight_line_geometry(28.6315, 77.2167, 28.6129, 77.2295)
    assert geom["type"] == "LineString"
    # GeoJSON is [lon, lat]
    coords = geom["coordinates"]
    assert len(coords) == 2
    assert coords[0][0] == 77.2167
    assert coords[0][1] == 28.6315
