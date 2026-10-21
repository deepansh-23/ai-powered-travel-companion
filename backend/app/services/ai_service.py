"""AI Service — dual-mode implementation using Google Gemini.

MOCK_MODE=true  → returns structured mock data from bundled JSON files.
MOCK_MODE=false → calls Gemini API to generate real, highly detailed itineraries
                  and area guides using verified places supplied by the backend.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.area import (
    AreaSection,
    AreaSummarizeRequest,
    AreaSummarizeResponse,
    QuickFacts,
)
from app.models.itinerary import (
    FoodStop,
    ItineraryDay,
    ItineraryRequest,
    ItineraryResponse,
    ItinerarySegment,
)

# -----------------------------------------------------------------------
# Gemini SDK Import
# -----------------------------------------------------------------------
_gemini_available = False
try:
  from google import genai as genai_client  # type: ignore
  from google.genai import types as genai_types  # type: ignore

  _gemini_available = True
  _use_legacy_genai = False
except ImportError:
  try:
    import google.generativeai as genai  # type: ignore

    _gemini_available = True
    _use_legacy_genai = True
  except ImportError:
    _use_legacy_genai = False
    _gemini_available = False

# -----------------------------------------------------------------------
# System Prompt (Enforces Rich Detail & Grounding)
# -----------------------------------------------------------------------
_GEMINI_SYSTEM_PROMPT = """You are a friendly, well-travelled local guide planning a trip for a friend.

Your output MUST be a detailed, rich, highly structured JSON response that breaks down the day logically.

VOICE (very important): write like a helpful friend, not a brochure or a manual.
- Talk to the traveller as "you". Use short, simple sentences and everyday words.
- Say what a place feels like and why it is worth the time ("Walk the old lanes and stop for chai"), not formal descriptions.
- Never use words like "itinerary segment", "utilise", "facilitate", "ambience", "curated", "iconic", "nestled" or "bustling".
- Keep every description to 1 or 2 short sentences. Day themes are short and fun (3 to 6 words).
- Practical tips should be concrete and kind ("Go early, it gets crowded after 11"), never vague.

FORMATTING & CONTENT GUIDELINES:
1. FOCUS & HIGHLIGHTS: For each segment or landmark, provide specific sub-fields:
   - "focus": Category/theme tags (e.g., "History & Hidden Memorials", "North Indian Vegetarian", "Shopping & Architecture").
   - "what_to_do": 1-2 short, friendly sentences on what to see or do there (plain words, no jargon).
   - "what_to_try": Specific culinary items to order at food stops (e.g., "Amritsari Stuffed Kulcha with spicy chole, fresh butter, and hot chai").
   - "transport": Concrete advice on transit (e.g., "Walk 2 minutes", "Take a ₹30–₹50 e-rickshaw ride").
   - "cost": Itemized entry fee or food cost per person in INR.

2. LOGICAL SEQUENCE:
   - Group places tightly by proximity (e.g., within 1–3 km radius).
   - Keep morning, afternoon, and evening flows contiguous.

3. PRACTICAL TRAVEL TIPS & BUDGETS:
   - Always include a "transport_note" covering local transit choices.
   - Label all costs clearly as estimates in INR.

4. GROUNDING SAFETY:
   - Use verified places provided where available. If verified list is empty or insufficient, draw from famous, well-established historical landmarks and culinary spots for the specified destination.

5. EVENINGS AND NIGHTS (make them real, not filler):
   - The evening starts around 5:30 PM and runs until the day naturally ends, anywhere between 9 PM and 11:30 PM. Do not stop at 8 PM, and never write "stroll around the local area" or "relax at a local place".
   - Every evening has at least 2 concrete stops in "evening.places", for example a sunset viewpoint, a night market, a lively street, a lakeside or riverside walk, a cultural spot or a show, plus dinner. Prefer verified places that suit the evening (markets, promenades, viewpoints, parks, entertainment venues, lively eateries).
   - Only mention a show, light display or event if it is a regular, well-known part of that place, and add "check timings". Never invent a specific event, performance or date.
   - Timing is flexible, not fixed. Leave a 7 to 9 hour rest window at the hotel: after a late night start the next day later (up to 9:30 AM), otherwise start between 8:00 and 9:00 AM. Give every segment a realistic "time_window"; the windows differ from day to day.

6. ABOUT EACH PLACE:
   - Every place needs "about": 1 or 2 friendly sentences saying what it is and why people visit (what kind of place it is, what it is known for, and roughly when it was built only if you are sure). Stay general when unsure and never invent facts, dates or numbers.
   - "what_to_do" is separate: what to do or see while you are there.
"""


class AIService:

  def __init__(self):
    self._client = None

  def _get_candidate_models(self) -> List[str]:
    configured = getattr(settings, "AI_MODEL", "gemini-3.8-flash").replace(
        "models/", ""
    )
    # As of this project's account on the Gemini free tier:
    # - gemini-2.5-flash / gemini-2.5-flash-lite: HARD BLOCKED — Google returns
    #   404 "no longer available to new users" and names these as the
    #   official replacements.
    # - gemini-pro-latest (-> gemini-3.1-pro): HARD BLOCKED on free tier —
    #   quota limit is 0 for this metric; never retry pro-tier models here
    #   without billing enabled.
    # - gemini-flash-latest: can 503 under temporary high demand; worth one
    #   quick retry, unlike the hard-blocked models above.
    candidates = [
        configured,
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
    ]
    seen = set()
    res = []
    for m in candidates:
      if m not in seen:
        seen.add(m)
        res.append(m)
    return res

  def _generate_with_fallback(self, prompt: str, system_prompt: Optional[str] = None) -> str:
    if not _gemini_available:
      raise RuntimeError(
          "AI service is not configured. Install google-genai: pip install"
          " google-genai"
      )
    api_key = getattr(settings, "GEMINI_API_KEY", "").strip()
    if not api_key:
      raise RuntimeError("Missing GEMINI_API_KEY in configuration.")

    import time

    models_to_try = self._get_candidate_models()
    errors: Dict[str, str] = {}

    for model_name in models_to_try:
      # Up to 2 attempts per model: a 503 ("high demand") is explicitly
      # framed by Google as transient and worth a quick retry; a 404
      # (model doesn't exist / not available to this account) or 429
      # (quota exhausted) will not resolve by retrying immediately, so
      # we fail fast on those and move to the next model instead.
      for attempt in range(2):
        try:
          if _use_legacy_genai:
            genai.configure(api_key=api_key)  # type: ignore
            model = genai.GenerativeModel(  # type: ignore
                model_name=model_name, system_instruction=system_prompt or _GEMINI_SYSTEM_PROMPT
            )
            resp = model.generate_content(prompt)
            return resp.text.strip()
          else:
            client = genai_client.Client(api_key=api_key)
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt or _GEMINI_SYSTEM_PROMPT,
                ),
            )
            return resp.text.strip()
        except Exception as exc:
          err_text = str(exc)
          errors[model_name] = f"{type(exc).__name__}: {exc}"
          is_transient_503 = (
              "503" in err_text or "UNAVAILABLE" in err_text
          )
          if is_transient_503 and attempt == 0:
            time.sleep(1.5)
            continue
          break  # permanent error (404/429/etc.) or retry exhausted

    detail = "; ".join(f"{m} -> {e}" for m, e in errors.items())
    raise RuntimeError(f"All candidate Gemini models failed. Details: {detail}")

  # -----------------------------------------------------------------------
  # Mock Data Methods
  # -----------------------------------------------------------------------

  def _load_mock_itinerary(self) -> Dict[str, Any]:
    path = settings.DATA_MOCK_DIR / "itinerary.json"
    if path.exists():
      with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    return {"templates": {}}

  # Vegetarian / vegan food stops used as substitutes in mock mode when the
  # template contains non-vegetarian options (e.g. the Hawksmoor steakhouse).
  _VEGETARIAN_DINNER_SUBSTITUTE = FoodStop(
      name="Saravana Bhavan",
      cuisine="South Indian Vegetarian",
      address="Local Branch",
      price_level="₹₹",
      recommendation="Masala dosa, idli-sambar, and filter coffee — pure vegetarian South Indian comfort food.",
  )
  _VEGAN_DINNER_SUBSTITUTE = FoodStop(
      name="Plant-Based Kitchen",
      cuisine="Vegan & Plant-Based",
      address="Local Branch",
      price_level="₹₹",
      recommendation="Buddha bowl with seasonal roasted vegetables, lentil dal, and cold-pressed juice.",
  )
  # Cuisine keywords that flag a food stop as non-vegetarian
  _NON_VEG_KEYWORDS = (
      "steak", "steakhouse", "seafood", "chicken", "lamb", "beef",
      "pork", "meat", "bacon", "prawn", "fish", "burger", "bbq",
  )

  def _adapt_food_stop_for_diet(
      self, stop: FoodStop, food_type: str
  ) -> FoodStop:
    """Return a vegetarian/vegan substitute if the stop contains meat."""
    if food_type not in ("vegetarian", "vegan"):
      return stop
    cuisine_lower = (stop.cuisine or "").lower()
    reco_lower = (stop.recommendation or "").lower()
    is_non_veg = any(
        kw in cuisine_lower or kw in reco_lower
        for kw in self._NON_VEG_KEYWORDS
    )
    if not is_non_veg:
      return stop
    if food_type == "vegan":
      return self._VEGAN_DINNER_SUBSTITUTE
    return self._VEGETARIAN_DINNER_SUBSTITUTE

  def _generate_mock_itinerary(self, req: ItineraryRequest) -> ItineraryResponse:
    data = self._load_mock_itinerary()
    template = data.get("templates", {}).get("default", {})

    dest_name = req.destination.strip().title()
    days_requested = req.duration_days
    travelers = req.travelers_count or 1
    per_day_per_person = int(req.budget_per_person_per_day)
    daily_total = per_day_per_person * travelers
    trip_total = daily_total * days_requested
    food_type = (req.food_type or "no-preference").lower().strip()

    all_days = template.get("days", [])
    selected_days: List[ItineraryDay] = []
    for i in range(days_requested):
      day_template = all_days[i % len(all_days)].copy()
      day_template["day_number"] = i + 1
      day_template["estimated_day_cost"] = (
          f"₹{daily_total:,} (₹{per_day_per_person:,} / person)"
      )
      day = ItineraryDay(**day_template)
      # Adapt non-vegetarian food stops to match the requested diet
      day = day.model_copy(update={
          "food_stop_lunch": self._adapt_food_stop_for_diet(
              day.food_stop_lunch, food_type
          ),
          "food_stop_dinner": self._adapt_food_stop_for_diet(
              day.food_stop_dinner, food_type
          ),
      })
      selected_days.append(day)

    title = f"{days_requested}-Day Itinerary for {dest_name}"
    overview = (
        f"A sample itinerary for {dest_name}. Running in mock mode — set"
        " MOCK_MODE=false in .env for live AI recommendations."
    )

    cost_breakdown = self._calculate_cost_breakdown(req, trip_total)

    return ItineraryResponse(
        title=title,
        destination=dest_name,
        source=req.source,
        departure_date=req.departure_date,
        return_date=req.return_date,
        selected_outbound_transport=req.selected_outbound_transport,
        selected_return_transport=req.selected_return_transport,
        selected_hotel=req.selected_hotel,
        cost_breakdown=cost_breakdown,
        duration_days=days_requested,
        estimated_budget_total=f"₹{cost_breakdown['overall_total_estimate']:,} total estimate",
        currency="INR",
        pace=req.pace.capitalize(),
        trip_overview=overview,
        days=selected_days,
        sources=["Sample mock data"],
        disclaimer="MOCK MODE active.",
        data_mode="mock",
    )

  def _calculate_cost_breakdown(
      self, req: ItineraryRequest, trip_total: float
  ) -> Dict[str, Any]:
    """Budget for the whole trip. Details come from utils.budget (live quotes vs estimates)."""
    from app.utils.budget import build_budget

    def _price(d: Any, key: str) -> Optional[float]:
      return d.get(key) if isinstance(d, dict) else None

    hotel = req.selected_hotel
    detail = build_budget(
        travelers=req.travelers_count or 1,
        days=req.duration_days,
        per_day_per_person=float(req.budget_per_person_per_day),
        outbound_pp=_price(req.selected_outbound_transport, "price"),
        return_pp=_price(req.selected_return_transport, "price"),
        hotel_total_per_room=_price(hotel, "total_price"),
        hotel_nightly=_price(hotel, "nightly_price"),
        rooms=req.rooms,
    )
    by_key = {l["key"]: l for l in detail["lines"]}
    return {
        # keys older screens and saved history items already use
        "outbound_transport_price": _price(req.selected_outbound_transport, "price"),
        "return_transport_price": _price(req.selected_return_transport, "price"),
        "hotel_total_price": by_key["stay"]["total"] if "stay" in by_key else None,
        "food_and_activities_estimate": detail["estimate_total"],
        "overall_total_estimate": detail["grand_total"],
        "per_person_estimate": detail["per_person_total"],
        "currency": "INR",
        "hotel_selected": "stay" in by_key,
        "transport_selected": "outbound" in by_key or "return" in by_key,
        # full breakdown for the "View total price breakdown" panel
        "detail": detail,
    }


  # -----------------------------------------------------------------------
  # Live Itinerary Generation
  # -----------------------------------------------------------------------

  async def _generate_live_itinerary(
      self,
      req: ItineraryRequest,
      verified_places: Optional[List[Dict[str, Any]]] = None,
  ) -> ItineraryResponse:
    dest_name = req.destination.strip().title()
    travelers = req.travelers_count or 1
    per_day_per_person = int(req.budget_per_person_per_day)
    daily_total = per_day_per_person * travelers
    trip_total = daily_total * req.duration_days

    places_json = (
        json.dumps(verified_places, ensure_ascii=False, indent=2)
        if verified_places
        else "[]"
    )

    # Day 1 may only start after the traveller has landed and settled in; the last day must end in time
    # for the journey home. These times are worked out in code (utils.day_timing), not left to the AI.
    from app.utils.day_timing import day_windows, window_prompt_lines
    windows = day_windows(
        req.selected_outbound_transport if isinstance(req.selected_outbound_transport, dict) else None,
        req.selected_return_transport if isinstance(req.selected_return_transport, dict) else None,
        req.duration_days,
    )
    transport_prompt_block = "\n".join(window_prompt_lines(windows, req.duration_days))


    food_prefs_str = ", ".join(req.food_preferences) if req.food_preferences else "Authentic regional specialties"

    modes_names = {"walking": "walking", "public": "public transit (bus/metro)", "taxi": "taxi / auto / e-rickshaw"}
    modes = req.transport_modes or {"public": ["walking", "public"], "walking": ["walking"], "driving": ["taxi"]}.get(
        req.transportation, ["walking", "public"])
    modes_line = ", ".join(modes_names[m] for m in modes if m in modes_names)
    wants_local = any("local special" in (f or "").lower() for f in (req.food_preferences or []))
    local_block = (
        "\n4. LOCAL SPECIALITIES REQUESTED: make most lunch, dinner and cafe stops places known for the area's "
        "famous local dishes and drinks. In each food stop's \"recommendation\" name the signature local dish to order. "
        "Still choose only from the verified places below.\n"
    ) if wants_local else "\n"

    schedule = list(req.area_schedule or [])
    if schedule:
      schedule_lines = "\n".join(f"Day {i + 1}: {a}" for i, a in enumerate(schedule))
      area_block = (
          "\nAREA SCHEDULE (the traveller stays in several places, so plan every day ONLY inside its area):\n"
          f"{schedule_lines}\n"
          "RULES: use only verified places whose \"area\" matches that day's area. On the first day in a new area, "
          "start with the transfer from the previous area (check out, travel, check in) and keep that day lighter. "
          "Keep each day's sights close together so travelling time stays low. Set \"area\" on every day.\n"
      )
    else:
      area_block = ""

    prompt = f"""Generate an exceptionally detailed {req.duration_days}-day travel itinerary for:

DESTINATION: {dest_name}
ORIGIN / SOURCE: {req.source or 'Not specified'}
TRAVELLERS: {travelers} ({req.travel_group_type})
BUDGET: ₹{per_day_per_person:,} per person/day (₹{trip_total:,} total estimate)
PACE: {req.pace}
INTERESTS: {', '.join(req.interests) if req.interests else 'Culture, Sights, Food'}
{area_block}
TRANSPORT & ACCOMMODATION CONSTRAINTS (TIME-AWARE):
{transport_prompt_block}

FOOD PRIORITIZATION:
1. Priority 1: Authentic, traditional local/regional cuisine of {dest_name}.
2. Dietary constraint: {req.food_type}.
3. Preferences: {food_prefs_str}.{local_block}
LOCAL TRANSPORT the traveller is happy with: {modes_line}. Keep the distance between stops reasonable for these.

VERIFIED PLACES FROM GEOAPIFY:
{places_json}

OUTPUT FORMAT — Respond ONLY with valid JSON (no markdown wrappers):
{{
  "title": "{req.duration_days}-Day Detailed Itinerary for {dest_name}",
  "trip_overview": "Practical overview detailing geographic scope, food highlights, and pace.",

  "days": [
    {{
      "day_number": 1,
      "theme": "Old City History, Architecture, Culture & Culinary Highlights",
      "area": "Name of the area this day is spent in",
      "estimated_day_cost": "₹{daily_total:,} total estimate",
      "morning": {{
        "time_window": "08:30 AM – 12:00 PM (times are examples: adjust them to the day)",
        "title": "Historical & Sacred Exploration",
        "focus": "Religious Place, Architecture, History",
        "description": "Detailed walkthrough of morning activities.",
        "what_to_do": "Clear actionable guide for the morning.",
        "transport_note": "Walk or e-rickshaw (~₹30–₹50)",
        "places": [
          {{
            "name": "Landmark Name",
            "category": "History / Architecture",
            "address": "Street / District",
            "duration": "1.5 hours",
            "admission": "Free entry / ₹10",
            "about": "What this place is and why people visit it, in 1-2 friendly sentences.",
            "what_to_do": "Specific highlights to see inside."
          }}
        ]
      }},
      "food_stop_lunch": {{
        "name": "Restaurant Name",
        "cuisine": "North Indian Vegetarian",
        "address": "Location / Landmark",
        "price_level": "₹₹",
        "recommendation": "Signature Dal Makhani, Lachha Paratha, and Lassi",
        "cost_per_person": "Approx. ₹350–₹450 per person"
      }},
      "afternoon": {{
        "time_window": "12:30 PM – 04:30 PM",
        "title": "Museums & Local Vibes",
        "focus": "History, Museums & Street Food",
        "description": "Afternoon itinerary description.",
        "what_to_do": "Detailed walkthrough of afternoon stops.",
        "transport_note": "Short walk or e-rickshaw",
        "places": []
      }},
      "food_stop_dinner": {{
        "name": "Evening Eatery / Sweet Shop",
        "cuisine": "Desserts & Local Snacks",
        "address": "Old City Lanes",
        "price_level": "₹",
        "recommendation": "Fresh hot crispy jalebis fried in pure ghee",
        "cost_per_person": "Approx. ₹80–₹120 per person"
      }},
      "evening": {{
        "time_window": "05:30 PM – 10:00 PM (ends when the plan naturally ends)",
        "title": "Sunset, Night Market & Late Dinner",
        "focus": "Night Views, Markets & Evening Life",
        "description": "Evening activities guide in 1-2 friendly sentences.",
        "what_to_do": "What to do across the evening.",
        "transport_note": "Walking distance",
        "places": [
          {{
            "name": "Sunset Viewpoint / Night Market (a verified place)",
            "category": "Viewpoint / Market",
            "address": "Street / District",
            "duration": "1.5 hours",
            "admission": "Free",
            "about": "What this place is and why it is lovely after dark.",
            "what_to_do": "Watch the sunset, then browse the stalls."
          }}
        ]
      }}
    }}
  ],
  "sources": ["Geoapify Places API", "Google Gemini AI"],
  "disclaimer": "All costs are estimates. Verify opening hours locally."
}}"""

    raw_text = self._generate_with_fallback(prompt)
    cleaned_text = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.MULTILINE
    ).strip()

    try:
      parsed = json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
      raise RuntimeError(
          f"The AI service returned an unexpected response format. ({exc})"
      )

    days_data = parsed.get("days", [])
    days: List[ItineraryDay] = []
    for d in days_data:
      try:
        day = ItineraryDay(
            day_number=d.get("day_number", len(days) + 1),
            theme=d.get("theme", "Exploration"),
            area=d.get("area") or (schedule[len(days)] if len(days) < len(schedule) else None),
            estimated_day_cost=d.get(
                "estimated_day_cost", f"₹{daily_total:,} estimate"
            ),
            morning=ItinerarySegment(**d["morning"])
            if "morning" in d
            else ItinerarySegment(
                time_window="08:00 AM – 12:00 PM",
                title="Morning",
                description="Explore local landmarks.",
                places=[],
            ),
            food_stop_lunch=FoodStop(**d["food_stop_lunch"])
            if "food_stop_lunch" in d
            else FoodStop(
                name="Local Lunch Spot",
                cuisine="Local Cuisine",
                recommendation="Try regional specialties.",
                price_level="₹₹",
            ),
            afternoon=ItinerarySegment(**d["afternoon"])
            if "afternoon" in d
            else ItinerarySegment(
                time_window="12:30 PM – 04:30 PM",
                title="Afternoon",
                description="Continue sightseeing.",
                places=[],
            ),
            food_stop_dinner=FoodStop(**d["food_stop_dinner"])
            if "food_stop_dinner" in d
            else FoodStop(
                name="Local Dinner Spot",
                cuisine="Local Cuisine",
                recommendation="Enjoy local evening delicacies.",
                price_level="₹₹",
            ),
            evening=ItinerarySegment(**d["evening"])
            if "evening" in d
            else ItinerarySegment(
                time_window="05:00 PM – 08:30 PM",
                title="Evening",
                description="Explore local markets.",
                places=[],
            ),
        )
        days.append(day)
      except Exception:
        continue

    cost_breakdown = self._calculate_cost_breakdown(req, trip_total)

    return ItineraryResponse(
        title=parsed.get(
            "title", f"{req.duration_days}-Day Itinerary for {dest_name}"
        ),
        destination=dest_name,
        source=req.source,
        departure_date=req.departure_date,
        return_date=req.return_date,
        selected_outbound_transport=req.selected_outbound_transport,
        selected_return_transport=req.selected_return_transport,
        selected_hotel=req.selected_hotel,
        cost_breakdown=cost_breakdown,
        duration_days=req.duration_days,
        estimated_budget_total=f"₹{cost_breakdown['overall_total_estimate']:,} total estimate",
        currency="INR",
        pace=req.pace.capitalize(),
        trip_overview=parsed.get(
            "trip_overview", f"A {req.pace} trip through {dest_name}."
        ),
        days=days,
        sources=["Geoapify Places API", "Google Gemini AI"],
        disclaimer="Provider prices are live quotes; other costs are estimates. Verify opening hours locally.",
        data_mode="live",
    )


  async def generate_itinerary(
      self,
      req: ItineraryRequest,
      verified_places: Optional[List[Dict[str, Any]]] = None,
  ) -> ItineraryResponse:
    if settings.MOCK_MODE:
      return self._generate_mock_itinerary(req)
    else:
      return await self._generate_live_itinerary(req, verified_places)

  # -----------------------------------------------------------------------
  # Mock Area Guide Methods
  # -----------------------------------------------------------------------

  def _load_mock_area(self) -> Dict[str, Any]:
    path = settings.DATA_MOCK_DIR / "area.json"
    if path.exists():
      with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    return {"areas": {}}

  def _generate_mock_area(self, req: AreaSummarizeRequest) -> AreaSummarizeResponse:
    data = self._load_mock_area()
    areas = data.get("areas", {})

    # Try exact match, then case-insensitive match, then first available
    area_key = req.area.strip().lower()
    template = areas.get(area_key)
    if not template:
      for k, v in areas.items():
        if k.lower() == area_key:
          template = v
          break
    if not template:
      # Fall back to the first area in the mock data
      if areas:
        template = next(iter(areas.values()))
      else:
        # Minimal fallback if mock file is empty
        return AreaSummarizeResponse(
            area_name=req.area.strip().title(),
            region="Unknown Region",
            character_summary=f"A guide for {req.area.strip().title()}. Running in mock mode — set MOCK_MODE=false in .env for live AI results.",
            quick_facts=QuickFacts(
                walkability="N/A",
                transit_connectivity="N/A",
                vibe="N/A",
                best_for="N/A",
                average_meal_cost="N/A",
            ),
            sections={},
            advantages=["Mock mode active — no live data available."],
            limitations=["Set MOCK_MODE=false for real results."],
            suitability=["All travellers"],
            source="Mock fallback (no matching area in sample data)",
            data_mode="mock",
        )

    # Parse sections into AreaSection objects
    raw_sections = template.get("sections", {})
    sections: Dict[str, AreaSection] = {}
    for key, sec_data in raw_sections.items():
      sections[key] = AreaSection(
          title=sec_data.get("title", key.replace("_", " ").title()),
          summary=sec_data.get("summary", ""),
          highlights=sec_data.get("highlights", []),
      )

    return AreaSummarizeResponse(
        area_name=template.get("area_name", req.area.strip().title()),
        region=template.get("region", ""),
        character_summary=template.get("character_summary", ""),
        quick_facts=QuickFacts(**template.get("quick_facts", {
            "walkability": "N/A",
            "transit_connectivity": "N/A",
            "vibe": "N/A",
            "best_for": "N/A",
            "average_meal_cost": "N/A",
        })),
        sections=sections,
        advantages=template.get("advantages", []),
        limitations=template.get("limitations", []),
        suitability=template.get("suitability", []),
        source=template.get("source", "Sample mock data"),
        data_mode="mock",
    )

  # -----------------------------------------------------------------------
  # Live Area Guide Generation
  # -----------------------------------------------------------------------

  async def _generate_live_area(
      self,
      req: AreaSummarizeRequest,
      verified_places: Optional[List[Dict[str, Any]]] = None,
  ) -> AreaSummarizeResponse:
    area_name = req.area.strip().title()

    places_json = (
        json.dumps(verified_places, ensure_ascii=False, indent=2)
        if verified_places
        else "[]"
    )

    prompt = f"""Generate a comprehensive neighborhood / area guide for:

AREA: {area_name}
RADIUS: {req.radius_km} km

VERIFIED PLACES FROM GEOAPIFY (use name, category, address only — do not invent facts):
{places_json}

OUTPUT FORMAT — Respond ONLY with valid JSON (no markdown wrappers):
{{
  "area_name": "{area_name}",
  "region": "State / Country / Region",
  "character_summary": "2-3 sentence vivid description of the area's character and feel.",
  "quick_facts": {{
    "walkability": "Score or description (e.g. Excellent 90/100)",
    "transit_connectivity": "Description of transit options",
    "vibe": "1-3 word vibe descriptor",
    "best_for": "Who this area suits best",
    "average_meal_cost": "Typical meal price range in local currency"
  }},
  "sections": {{
    "food": {{
      "title": "Dining & Street Food",
      "summary": "Overview of the food scene.",
      "highlights": ["Place 1", "Place 2", "Place 3"]
    }},
    "cafes": {{
      "title": "Specialty Cafés & Work Spots",
      "summary": "Overview of café culture.",
      "highlights": ["Café 1", "Café 2"]
    }},
    "shopping": {{
      "title": "Retail & Markets",
      "summary": "Shopping overview.",
      "highlights": ["Market 1", "Shop 1"]
    }},
    "hospitals_pharmacies": {{
      "title": "Medical Care & Pharmacies",
      "summary": "Healthcare access overview.",
      "highlights": ["Hospital 1", "Pharmacy 1"]
    }},
    "atms": {{
      "title": "Banking & ATMs",
      "summary": "Banking access.",
      "highlights": ["ATM location 1"]
    }},
    "attractions": {{
      "title": "Historic & Cultural Landmarks",
      "summary": "Key attractions overview.",
      "highlights": ["Landmark 1", "Landmark 2"]
    }},
    "parks": {{
      "title": "Green Spaces & Recreation",
      "summary": "Parks overview.",
      "highlights": ["Park 1"]
    }},
    "transport": {{
      "title": "Public Transportation",
      "summary": "Transit options overview.",
      "highlights": ["Station 1", "Bus Route 1"]
    }}
  }},
  "advantages": [
    "Advantage 1",
    "Advantage 2",
    "Advantage 3"
  ],
  "limitations": [
    "Limitation 1",
    "Limitation 2"
  ],
  "suitability": [
    "Suited for solo travellers...",
    "Suited for couples..."
  ],
  "source": "Geoapify Places API & Google Gemini AI"
}}"""

    raw_text = self._generate_with_fallback(prompt)
    cleaned_text = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.MULTILINE
    ).strip()

    try:
      parsed = json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
      raise RuntimeError(
          f"The AI service returned an unexpected response format. ({exc})"
      )

    # Parse sections defensively
    raw_sections = parsed.get("sections", {})
    sections: Dict[str, AreaSection] = {}
    for key, sec_data in raw_sections.items():
      if isinstance(sec_data, dict):
        sections[key] = AreaSection(
            title=sec_data.get("title", key.replace("_", " ").title()),
            summary=sec_data.get("summary", ""),
            highlights=sec_data.get("highlights", []),
        )

    # Parse quick_facts defensively
    raw_qf = parsed.get("quick_facts", {})
    if not isinstance(raw_qf, dict):
      raw_qf = {}
    quick_facts = QuickFacts(
        walkability=raw_qf.get("walkability", "N/A"),
        transit_connectivity=raw_qf.get("transit_connectivity", "N/A"),
        vibe=raw_qf.get("vibe", "N/A"),
        best_for=raw_qf.get("best_for", "N/A"),
        average_meal_cost=raw_qf.get("average_meal_cost", "N/A"),
    )

    return AreaSummarizeResponse(
        area_name=parsed.get("area_name", area_name),
        region=parsed.get("region", ""),
        character_summary=parsed.get("character_summary", f"A guide for {area_name}."),
        quick_facts=quick_facts,
        sections=sections,
        advantages=parsed.get("advantages", []),
        limitations=parsed.get("limitations", []),
        suitability=parsed.get("suitability", []),
        source=parsed.get("source", "Geoapify Places API & Google Gemini AI"),
        data_mode="live",
    )

  # -----------------------------------------------------------------------
  # Public Area Guide Entry Point
  # -----------------------------------------------------------------------

  async def summarize_area(
      self,
      req: AreaSummarizeRequest,
      verified_places: Optional[List[Dict[str, Any]]] = None,
  ) -> AreaSummarizeResponse:
    if settings.MOCK_MODE:
      return self._generate_mock_area(req)
    else:
      return await self._generate_live_area(req, verified_places)


ai_service = AIService()