"""Deterministic Transport Recommendation scoring and ranking (Section 10, 31, 33A).
Evaluates price, duration, stops, mode preference, and convenience.
Gemini must not decide this.
"""

from typing import List, Optional
from app.models.transport import TransportOption


class TransportRecommendationService:
    def score_options(
        self,
        options: List[TransportOption],
        preference: str = "best-overall"
    ) -> List[TransportOption]:
        """Calculates deterministic score and recommendation reason for each transport option.
        Lower score = better match / ranked higher.
        """
        if not options:
            return []

        # Find min/max price and duration across all available options
        priced = [o for o in options if o.price is not None and o.price > 0]
        min_p = min((o.price for o in priced), default=1.0)
        max_p = max((o.price for o in priced), default=1.0)
        p_span = (max_p - min_p) if max_p > min_p else 1.0

        durations = [o.duration_minutes for o in options if o.duration_minutes > 0]
        min_d = min(durations, default=1)
        max_d = max(durations, default=1)
        d_span = (max_d - min_d) if max_d > min_d else 1.0

        pref_key = preference.lower().replace("_", "-")

        for opt in options:
            # Normalized price factor (0 = lowest, 1 = highest)
            norm_p = ((opt.price - min_p) / p_span) if opt.price is not None else 0.6
            # Normalized duration factor (0 = shortest, 1 = longest)
            norm_d = ((opt.duration_minutes - min_d) / d_span) if opt.duration_minutes else 0.5
            # Stops penalty
            stops_penalty = opt.stops * 0.15

            # Calculate composite score based on user preference
            if pref_key == "cheapest":
                # Heavily weight price (85%), slight weight on duration (15%)
                score = (norm_p * 0.85) + (norm_d * 0.15) + (stops_penalty * 0.05)
                reason = f"Cheapest available fare at {opt.currency} {int(opt.price):,}" if opt.price else "Affordable option"

            elif pref_key == "fastest":
                # Heavily weight duration (85%), slight weight on price (15%)
                score = (norm_d * 0.85) + (norm_p * 0.15) + stops_penalty
                dur_str = opt.duration_formatted or f"{opt.duration_minutes}m"
                reason = f"Fastest transit duration of {dur_str}"

            elif pref_key == "prefer-flight":
                # Balanced score with mode bonus for flight
                base_score = (norm_p * 0.45) + (norm_d * 0.45) + stops_penalty
                mode_bonus = -0.40 if opt.mode == "flight" else 0.30
                score = base_score + mode_bonus
                if opt.mode == "flight":
                    reason = f"Flight preferred: fast travel time ({opt.duration_formatted or f'{opt.duration_minutes}m'})"
                else:
                    reason = f"Alternative rail option ({opt.duration_formatted or f'{opt.duration_minutes}m'})"

            elif pref_key == "prefer-train":
                # Balanced score with mode bonus for train
                base_score = (norm_p * 0.45) + (norm_d * 0.45) + stops_penalty
                mode_bonus = -0.40 if opt.mode == "train" else 0.30
                score = base_score + mode_bonus
                if opt.mode == "train":
                    price_str = f" at {opt.currency} {int(opt.price):,}" if opt.price else ""
                    reason = f"Train preferred: comfortable direct railway travel{price_str}"
                else:
                    reason = f"Alternative flight option ({opt.duration_formatted or f'{opt.duration_minutes}m'})"

            elif pref_key in ("best-overall", "no-preference"):
                # Balanced weight: 45% price, 45% duration, 10% stops
                score = (norm_p * 0.45) + (norm_d * 0.45) + stops_penalty
                dur_str = opt.duration_formatted or f"{opt.duration_minutes}m"
                price_str = f"{opt.currency} {int(opt.price):,}" if opt.price else "N/A"
                stops_str = "direct" if opt.stops == 0 else f"{opt.stops} stop"
                reason = f"Optimal balance of travel time ({dur_str}), price ({price_str}), and {stops_str} routing"

            else:
                score = (norm_p * 0.5) + (norm_d * 0.5) + stops_penalty
                reason = "Balanced travel selection"

            opt.score = round(score, 4)
            opt.recommendation_reason = reason

        # Sort by score ascending (lowest score is best)
        sorted_opts = sorted(options, key=lambda o: (o.score if o.score is not None else 999.0))

        # Assign badges for user clarity
        if sorted_opts:
            top = sorted_opts[0]
            if pref_key == "cheapest":
                top.recommendation_badge = "Cheapest"
            elif pref_key == "fastest":
                top.recommendation_badge = "Fastest"
            elif pref_key == "prefer-flight":
                top.recommendation_badge = "Top Flight Pick"
            elif pref_key == "prefer-train":
                top.recommendation_badge = "Top Train Pick"
            else:
                top.recommendation_badge = "Best Overall"

        return sorted_opts


transport_recommendation_service = TransportRecommendationService()
