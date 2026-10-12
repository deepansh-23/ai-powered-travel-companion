"""Automated tests for Hotel recommendation labels and sorting (Section 33A-4).
"""

import pytest
from app.models.hotel import HotelOption
from app.services.hotel_recommendation_service import hotel_recommendation_service


@pytest.fixture
def hotel_fixtures():
    h_cheap = HotelOption(
        id="h_cheap",
        name="Budget Inn",
        nightly_price=1200.0,
        total_price=2400.0,
        rating=3.6,
        review_count=180
    )
    h_luxury = HotelOption(
        id="h_luxury",
        name="Grand Luxury Palace",
        nightly_price=9500.0,
        total_price=19000.0,
        rating=4.9,
        review_count=1500
    )
    h_value = HotelOption(
        id="h_value",
        name="Comfort Suites Central",
        nightly_price=2800.0,
        total_price=5600.0,
        rating=4.6,
        review_count=820
    )
    return [h_cheap, h_luxury, h_value]


def test_hotel_recommendation_labels(hotel_fixtures):
    labeled = hotel_recommendation_service.compute_labels_and_recommendations(hotel_fixtures)

    cheap = next(h for h in labeled if h.id == "h_cheap")
    assert "Cheapest" in cheap.recommendation_labels
    assert "Lowest nightly rate" in cheap.recommendation_reason

    luxury = next(h for h in labeled if h.id == "h_luxury")
    assert "Best Rated" in luxury.recommendation_labels
    assert "★ 4.9" in luxury.recommendation_reason

    value = next(h for h in labeled if h.id == "h_value")
    assert "Best Value" in value.recommendation_labels
    assert "balance" in value.recommendation_reason.lower()


def test_hotel_sorting_lowest_price(hotel_fixtures):
    sorted_hotels = hotel_recommendation_service.sort_hotels(hotel_fixtures, sort_by="lowest_price")
    prices = [h.nightly_price for h in sorted_hotels]
    assert prices == [1200.0, 2800.0, 9500.0]


def test_hotel_sorting_highest_rating(hotel_fixtures):
    sorted_hotels = hotel_recommendation_service.sort_hotels(hotel_fixtures, sort_by="highest_rating")
    ratings = [h.rating for h in sorted_hotels]
    assert ratings == [4.9, 4.6, 3.6]


def test_hotel_sorting_most_reviewed(hotel_fixtures):
    sorted_hotels = hotel_recommendation_service.sort_hotels(hotel_fixtures, sort_by="most_reviewed")
    reviews = [h.review_count for h in sorted_hotels]
    assert reviews == [1500, 820, 180]
