"""Batch C: real evenings, flexible timing, an 'About' line for every place, night-friendly places."""

import asyncio
from unittest.mock import patch

from app.models.itinerary import ItineraryPlaceItem, ItineraryRequest
from app.routes import itinerary as itin_routes
from app.services import ai_service as ai_mod
from app.services.pdf_service import pdf_service

BASE = dict(destination="Jaipur", source="Delhi", departure_date="2099-03-10", return_date="2099-03-12",
            duration_days=3, budget_per_person_per_day=3000, travelers_count=2)

PLAN_JSON = ('{"title": "t", "trip_overview": "o", "days": [{"day_number": 1, "theme": "x", '
             '"morning": {"time_window": "9", "title": "m", "description": "d", "places": '
             '[{"name": "Hawa Mahal", "category": "History", "about": "A pink palace front.", "what_to_do": "Look up."}]}, '
             '"evening": {"time_window": "5:30 PM – 10:30 PM", "title": "e", "description": "d", "places": '
             '[{"name": "Johari Bazaar", "category": "Market", "about": "A jewellery market.", "what_to_do": "Browse."}]}}]}')


def _capture_prompt(**extra):
    seen = {}

    def fake(self, prompt, system_prompt=None):
        seen["prompt"] = prompt
        return PLAN_JSON

    req = ItineraryRequest(**BASE, **extra)
    with patch.object(ai_mod.AIService, "_generate_with_fallback", fake):
        resp = asyncio.run(ai_mod.ai_service._generate_live_itinerary(req, verified_places=[
            {"name": "Hawa Mahal", "category": "tourism.sights", "latitude": 26.92, "longitude": 75.82},
            {"name": "Johari Bazaar", "category": "commercial.marketplace", "latitude": 26.92, "longitude": 75.83}]))
    return seen["prompt"], resp


def test_instructions_ask_for_real_flexible_evenings_and_about_lines():
    sp = ai_mod._GEMINI_SYSTEM_PROMPT
    assert "EVENINGS AND NIGHTS" in sp and "between 9 PM and 11:30 PM" in sp and "7 to 9 hour rest window" in sp
    assert "never write \"stroll around the local area\"" in sp and "Never invent a specific event" in sp
    assert "ABOUT EACH PLACE" in sp and "never invent facts, dates or numbers" in sp


def test_prompt_schema_gives_the_evening_places_and_about():
    prompt, _ = _capture_prompt()
    evening = prompt[prompt.index('"evening": {'):]
    assert '"places": [' in evening and '"about":' in evening
    assert "(times are examples: adjust them to the day)" in prompt
    assert "05:30 PM" in prompt and "08:30 PM" not in prompt  # no more fixed 8:30 PM evening end


def test_about_and_evening_places_survive_into_the_response():
    _, resp = _capture_prompt()
    day = resp.days[0]
    assert day.morning.places[0].about == "A pink palace front." and day.morning.places[0].what_to_do == "Look up."
    assert day.evening.places[0].name == "Johari Bazaar" and day.evening.places[0].about
    assert ItineraryPlaceItem(name="x", category="y").about is None


def test_night_friendly_places_are_requested_with_a_safe_fallback():
    calls = []

    def fake(lat, lon, radius, categories, limit=40):
        calls.append((categories, limit))
        if "commercial.marketplace" in categories:
            raise RuntimeError("Geoapify rejected a category")
        return ["feature"]

    with patch.object(itin_routes, "_fetch_geoapify_places", fake):
        assert itin_routes._fetch_places_with_nightlife(26.9, 75.8, 5000, 40) == ["feature"]
    assert "commercial.marketplace" in calls[0][0] and "catering.bar" in calls[0][0] and calls[0][1] > 40
    assert "commercial.marketplace" not in calls[1][0] and calls[1][1] == 40  # fell back to the normal list

    calls.clear()
    with patch.object(itin_routes, "_fetch_geoapify_places", lambda *a, **k: ["ok"]):
        assert itin_routes._fetch_places_with_nightlife(26.9, 75.8, 5000, 40) == ["ok"]


def test_full_pdf_shows_what_each_place_is():
    content = {"title": "T", "destination": "Jaipur", "duration_days": 1, "days": [{
        "day_number": 1, "theme": "Pink city", "morning": {"time_window": "9", "title": "m", "description": "d",
        "places": [{"name": "Hawa Mahal", "about": "A pink palace front & more."}]}}]}
    assert pdf_service.generate_itinerary_pdf_bytes("T", content)[:4] == b"%PDF"
