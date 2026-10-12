"""Tests for backend validation rules (Section 27, Section 50.7).
"""

import pytest
from app.utils.validation import (
    sanitize_place_name,
    validate_website_url,
    validate_rating,
    deduplicate_places
)


def test_sanitize_place_name():
    # Valid names
    assert sanitize_place_name("India Gate") == "India Gate"
    assert sanitize_place_name("  The Midland Hotel  ") == "The Midland Hotel"

    # Invalid / generic placeholder names
    assert sanitize_place_name(None) is None
    assert sanitize_place_name("") is None
    assert sanitize_place_name("   ") is None
    assert sanitize_place_name("unnamed") is None
    assert sanitize_place_name("Unnamed Place") is None
    assert sanitize_place_name("n/a") is None
    assert sanitize_place_name("test") is None
    assert sanitize_place_name("placeholder") is None


def test_validate_website_url():
    # Valid absolute http/https URLs
    assert validate_website_url("https://manchesterartgallery.org") == "https://manchesterartgallery.org"
    assert validate_website_url("http://dishoom.com/manchester") == "http://dishoom.com/manchester"
    assert validate_website_url("www.afflecks.com") == "https://www.afflecks.com"

    # Invalid / blocked / dangerous URLs
    assert validate_website_url(None) is None
    assert validate_website_url("") is None
    assert validate_website_url("javascript:alert(1)") is None
    assert validate_website_url("data:text/html;base64,foo") is None
    assert validate_website_url("http://localhost:8080/place") is None
    assert validate_website_url("http://127.0.0.1:3000") is None
    assert validate_website_url("https://example.com/test") is None
    assert validate_website_url("https://sub.example.org/venue") is None


def test_validate_rating():
    # Valid rating with source
    r, src, count = validate_rating(4.5, "Google Reviews", 1200)
    assert r == 4.5
    assert src == "Google Reviews"
    assert count == 1200

    # Missing source -> must return None, NEVER default to 0
    r, src, count = validate_rating(4.5, None, 100)
    assert r is None
    assert src is None

    # Rating out of range (0 to 5)
    r, src, _ = validate_rating(5.5, "TripAdvisor")
    assert r is None
    r, src, _ = validate_rating(-1.0, "TripAdvisor")
    assert r is None

    # None rating
    r, src, _ = validate_rating(None, "TripAdvisor")
    assert r is None


def test_deduplicate_places():
    places = [
        {"name": "Midland Hotel", "address": "16 Peter St", "category": "hotel"},
        {"name": "Midland Hotel", "address": "16 Peter St", "category": "hotel"},  # duplicate
        {"name": "Midland Hotel", "address": "Different Street", "category": "hotel"},  # different location
        {"name": "Unnamed", "address": "Some Street", "category": "hotel"},  # unnamed place should be dropped
    ]
    deduped = deduplicate_places(places)
    assert len(deduped) == 2
    assert deduped[0]["name"] == "Midland Hotel"
    assert deduped[1]["address"] == "Different Street"
