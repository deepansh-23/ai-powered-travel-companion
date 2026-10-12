"""Deterministic Hotel Recommendation and Sorting logic (Section 7A, 10, 31).
Backend code calculates Cheapest, Best Rated, and Best Value labels and reasons.
Gemini must not decide this.
"""

from typing import List, Optional
from app.models.hotel import HotelOption


class HotelRecommendationService:
    def compute_labels_and_recommendations(self, hotels: List[HotelOption]) -> List[HotelOption]:
        """Calculates 'Cheapest', 'Best Rated', and 'Best Value' labels and reasons."""
        if not hotels:
            return hotels

        priced_hotels = [h for h in hotels if h.nightly_price is not None and h.nightly_price > 0]
        rated_hotels = [h for h in hotels if h.rating is not None and h.rating > 0]

        cheapest_hotel: Optional[HotelOption] = None
        if priced_hotels:
            cheapest_hotel = min(priced_hotels, key=lambda h: h.nightly_price or float("inf"))

        best_rated_hotel: Optional[HotelOption] = None
        if rated_hotels:
            # Sort by rating desc, then review_count desc
            best_rated_hotel = max(
                rated_hotels,
                key=lambda h: (h.rating or 0.0, h.review_count or 0)
            )

        best_value_hotel: Optional[HotelOption] = None
        if priced_hotels and rated_hotels:
            # Calculate value score = rating / log(price) or normalized rating vs price
            min_price = min(h.nightly_price for h in priced_hotels)
            max_price = max(h.nightly_price for h in priced_hotels)
            price_range = max_price - min_price if max_price > min_price else 1.0

            def value_score(h: HotelOption) -> float:
                r = (h.rating or 3.0) / 5.0
                norm_price = (h.nightly_price - min_price) / price_range
                # 60% weight on rating quality, 40% weight on price affordability
                return (r * 0.6) + ((1.0 - norm_price) * 0.4)

            candidate_value = [h for h in priced_hotels if (h.rating or 0) >= 3.5]
            if candidate_value:
                best_value_hotel = max(candidate_value, key=value_score)
            else:
                best_value_hotel = max(priced_hotels, key=value_score)

        for h in hotels:
            labels = []
            reasons = []

            if cheapest_hotel and h.id == cheapest_hotel.id:
                labels.append("Cheapest")
                reasons.append(f"Lowest nightly rate at {h.currency} {int(h.nightly_price):,}")

            if best_rated_hotel and h.id == best_rated_hotel.id:
                labels.append("Best Rated")
                rev_str = f" from {h.review_count:,} reviews" if h.review_count else ""
                reasons.append(f"Top guest rating of ★ {h.rating}{rev_str}")

            if best_value_hotel and h.id == best_value_hotel.id and h.id != cheapest_hotel.id:
                labels.append("Best Value")
                reasons.append(f"Optimal balance of high review score (★ {h.rating}) and competitive nightly pricing")

            h.recommendation_labels = labels
            if reasons:
                h.recommendation_reason = " • ".join(reasons)

        return hotels

    def sort_hotels(self, hotels: List[HotelOption], sort_by: str) -> List[HotelOption]:
        """Sorts hotels deterministically based on user filter criteria."""
        if sort_by == "lowest_price":
            return sorted(
                hotels,
                key=lambda h: (h.nightly_price is None, h.nightly_price or float("inf"), -(h.rating or 0))
            )
        elif sort_by == "highest_rating":
            return sorted(
                hotels,
                key=lambda h: (-(h.rating or 0.0), -(h.review_count or 0), h.nightly_price or float("inf"))
            )
        elif sort_by == "most_reviewed":
            return sorted(
                hotels,
                key=lambda h: (-(h.review_count or 0), -(h.rating or 0.0))
            )
        # Default / relevance: prioritize labeled options and rating
        return sorted(
            hotels,
            key=lambda h: (
                0 if "Best Value" in h.recommendation_labels else
                (1 if "Cheapest" in h.recommendation_labels else
                 (2 if "Best Rated" in h.recommendation_labels else 3)),
                -(h.rating or 0.0),
                h.nightly_price or float("inf")
            )
        )


hotel_recommendation_service = HotelRecommendationService()
