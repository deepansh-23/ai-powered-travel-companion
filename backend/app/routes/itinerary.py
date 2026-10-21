"""Itinerary planner API route.

In live mode (MOCK_MODE=false), this route:
1. Geocodes the destination via Geoapify
2. Fetches nearby places from Geoapify (using the user's radius)
3. Passes verified places to Gemini for itinerary organization
4. Returns the result to the frontend
Never silently falls back to Manchester mock data in live mode.
"""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.itinerary import (
    FinalizeRequest,
    ItineraryRequest,
    ItineraryResponse,
    ScopeRequest,
    ScopeResponse,
)
from app.services.ai_service import ai_service
from app.services.geocoding_service import geocoding_service
from app.services.places_service import (
    _PLACES_CATEGORIES,
    _fetch_geoapify_places,
    _geoapify_feature_to_dict,
)
from app.security import require_user
from app.services.directions_service import enrich_itinerary
from app.services.scope_service import scope_service
from app.utils.budget import build_budget
from app.utils.day_timing import (
    arrival_card, cab_estimate, departure_card, hotel_change_card, transfer_card, _short_place,
)
from app.utils.trip_planner import allocate_days, block_transfers, plan_stay_blocks, transfer_needs_choice
from fastapi import APIRouter, HTTPException, status, Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itinerary", tags=["Itinerary"])


_JUNK_NAMES = ("unnamed place", "unknown", "unnamed road", "n/a", "null")

# Extra place types that stay open or lively after dark, so evenings can be real plans
_NIGHT_EXTRA = "commercial.marketplace,entertainment.cinema,catering.bar,catering.pub"


def _fetch_places_with_nightlife(lat: float, lon: float, radius_m: int, limit: int) -> List[Any]:
  """Places for the plan, including evening-friendly ones. If Geoapify rejects the wider list the
  normal list is used, so planning never breaks because of the extras."""
  try:
    return _fetch_geoapify_places(lat, lon, radius_m, f"{_PLACES_CATEGORIES},{_NIGHT_EXTRA}", limit=limit + 15)
  except Exception as exc:
    logger.info(f"Evening-friendly places unavailable, using the normal list: {exc}")
    return _fetch_geoapify_places(lat, lon, radius_m, _PLACES_CATEGORIES, limit=limit)


def _to_verified(features: List[Any], area: Optional[str] = None) -> List[Dict[str, Any]]:
  out = []
  for f in features:
    p = _geoapify_feature_to_dict(f)
    name = (p.get("name") or "").strip()
    if not name or name.lower() in _JUNK_NAMES:
      continue
    item = {
        "name": p["name"],
        "address": p.get("address"),
        "category": p.get("category", "general"),
        "latitude": p.get("latitude"),
        "longitude": p.get("longitude"),
        "website": p.get("website"),
    }
    if area:
      item["area"] = area
    out.append(item)
  return out


async def _places_for_area(area: str, radius_km: float, limit: int) -> List[Dict[str, Any]]:
  """Geocode one area and fetch its real places (blocking calls run in a thread)."""
  center = await asyncio.to_thread(geocoding_service.resolve_center, location=area)
  features = await asyncio.to_thread(
      _fetch_places_with_nightlife, center.latitude, center.longitude, int(radius_km * 1000), limit
  )
  return _to_verified(features, area)


def _clean_areas(req: ItineraryRequest) -> List[str]:
  """Areas in visiting order: arrival city first for state/country trips, never more than the day count allows."""
  areas: List[str] = []
  for a in ([req.arrival_city] if req.scope_kind in ("state", "country") and req.arrival_city else []) + list(req.areas or []):
    a = (a or "").strip()
    if a and a.lower() not in {x.lower() for x in areas}:
      areas.append(a)
  return areas


def _day_meta(response: ItineraryResponse) -> List[Dict[str, Any]]:
  meta = []
  for d in response.days:
    points, names = [], []
    for seg in (d.morning, d.afternoon, d.evening):
      for p in seg.places or []:
        names.append(p.name)
        if p.latitude is not None and p.longitude is not None:
          points.append((p.latitude, p.longitude))
    for f in (d.food_stop_lunch, d.food_stop_dinner):
      if f.latitude is not None and f.longitude is not None:
        points.append((f.latitude, f.longitude))
    meta.append({"day_number": d.day_number, "area": d.area or response.destination, "points": points, "places": names[:3]})
  return meta


@router.post("/scope", response_model=ScopeResponse, dependencies=[Depends(require_user)])
async def plan_scope(req: ScopeRequest):
  """Is the destination a city, state or country, and what should the traveller be asked?"""
  return await scope_service.scope(req.destination, req.duration_days, req.kind)


@router.post("/generate", response_model=ItineraryResponse, dependencies=[Depends(require_user)])
async def generate_itinerary(req: ItineraryRequest):
  """Generate a multi-day itinerary WITHOUT hotels.

  The response contains `stay_blocks`: groups of days that share one hotel. The traveller picks a hotel
  for each stay near that stay's places, then calls /finalize.
  """
  verified_places: Optional[List[Dict[str, Any]]] = None
  notices: List[str] = []
  areas = _clean_areas(req) or [req.destination.strip()]
  multi = len(areas) > 1 or req.scope_kind in ("state", "country")

  if multi and not req.areas and len(areas) < 2 and req.scope_kind in ("state", "country"):
    # Travellers who skipped the choice: let the planner pick a few well-known places
    try:
      sc = await scope_service.scope(req.destination, req.duration_days, req.scope_kind)
      for item in sc.suggestions[: max(0, sc.recommended_areas - len(areas))]:
        if item["name"].lower() not in {a.lower() for a in areas}:
          areas.append(item["name"])
      if len(areas) > 1:
        notices.append("You did not pick places, so the planner chose: " + ", ".join(areas) + ".")
    except Exception as exc:
      logger.info(f"Automatic area choice unavailable: {exc}")

  if not settings.MOCK_MODE:
    if not multi:
      # --- single area (unchanged behaviour) ---
      try:
        center = geocoding_service.resolve_center(location=req.destination)
      except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
      except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
      try:
        features = _fetch_places_with_nightlife(
            center.latitude, center.longitude, int(req.radius_km * 1000), 40)
        verified_places = _to_verified(features)
      except Exception as exc:
        logger.warning(f"Failed to fetch Geoapify places: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=("Could not fetch real places for this destination from Geoapify."
                    " Please retry; no itinerary was generated to avoid invented places."),
        )
      if not verified_places:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"No real places were found near '{req.destination}'."
                    " Try a larger radius or a different destination."),
        )
      req.area_schedule = [areas[0]] * req.duration_days
    else:
      # --- several areas: real places for each, then split the days between them ---
      radius = max(req.radius_km, 8.0)
      results = await asyncio.gather(
          *(_places_for_area(a, radius, 30) for a in areas[:6]), return_exceptions=True)
      per_area: Dict[str, List[Dict[str, Any]]] = {}
      for a, res in zip(areas[:6], results):
        if isinstance(res, Exception) or not res:
          notices.append(f"No real places could be found for '{a}', so it was left out of the plan.")
        else:
          per_area[a] = res
      if not per_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No real places were found for the places you chose. Check the spelling or pick other places.",
        )
      used = list(per_area)
      weights = [float(min(len(per_area[a]), 30)) for a in used]
      req.area_schedule = allocate_days(used, req.duration_days, weights)
      verified_places = [p for a in used for p in per_area[a]]
      areas = list(dict.fromkeys(req.area_schedule))
  else:
    req.area_schedule = allocate_days(areas, req.duration_days) or [areas[0]] * req.duration_days
    areas = list(dict.fromkeys(req.area_schedule))

  try:
    response = await ai_service.generate_itinerary(req, verified_places=verified_places)
    try:
      enrich_itinerary(response, req, verified_places)
    except Exception as exc:  # directions are a bonus: never fail the itinerary
      logger.warning(f"Could not add stop-to-stop directions: {exc}")

    # Which days share a hotel, and how far apart the stays are
    schedule = req.area_schedule or []
    for i, day in enumerate(response.days):
      if i < len(schedule):
        day.area = schedule[i]
    response.areas = areas
    response.stay_blocks = plan_stay_blocks(_day_meta(response), req.departure_date)
    response.transfers = block_transfers(response.stay_blocks)
    for t in response.transfers:
      to_block = next((b for b in response.stay_blocks if b["index"] == t["to_stay"]), None)
      t["date"] = (to_block or {}).get("check_in")           # the day the traveller moves
      t["needs_choice"] = transfer_needs_choice(req.scope_kind, t["distance_km"])
    response.notices = notices
    return response
  except (ValueError, RuntimeError) as exc:
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
  except HTTPException:
    raise
  except Exception as exc:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to generate itinerary: {str(exc)}",
    )


def _hotel_xy(hotel: Optional[Dict[str, Any]]) -> Optional[tuple]:
  if hotel and hotel.get("latitude") is not None and hotel.get("longitude") is not None:
    return (float(hotel["latitude"]), float(hotel["longitude"]))
  return None


async def _terminal_xy(leg: Optional[Dict[str, Any]], which: str) -> Optional[tuple]:
  """(lat, lon) of the airport where a flight lands / leaves, or None. Trains and unknown places return None
  (a typical transfer time is used instead and labelled as such)."""
  if settings.MOCK_MODE or not leg or str(leg.get("mode") or "").lower() != "flight":
    return None
  name = _short_place(leg.get("destination" if which == "arrive" else "origin"))
  if not name:
    return None
  try:
    c = await asyncio.to_thread(geocoding_service.resolve_center, location=name)
    return (c.latitude, c.longitude)
  except Exception as exc:
    logger.info(f"Could not locate '{name}' for the transfer estimate: {exc}")
    return None


def _choice_by_stay(req: FinalizeRequest) -> Dict[int, Dict[str, Any]]:
  """to_stay -> {'mode', 'option'} for the journeys the traveller chose between stays."""
  return {c.to_stay: {"mode": c.mode, "option": c.option or {}} for c in req.transfer_choices}


async def _build_day_notes(it: ItineraryResponse, hotels_by_day: Dict[int, Dict[str, Any]],
                           choices: Optional[Dict[int, Dict[str, Any]]] = None) -> None:
  """Arrival card on day 1, 'changing hotel' cards on moving days, departure card on the last day."""
  for d in it.days:
    d.notes = []
  if not it.days:
    return
  landing = (it.areas[0] if it.areas else it.destination) or ""
  first, last = it.days[0], it.days[-1]
  ob = it.selected_outbound_transport if isinstance(it.selected_outbound_transport, dict) else None
  ib = it.selected_return_transport if isinstance(it.selected_return_transport, dict) else None

  if ob:
    hotel = hotels_by_day.get(first.day_number)
    cab = cab_estimate(await _terminal_xy(ob, "arrive"), _hotel_xy(hotel))
    first.notes.append(arrival_card(ob, hotel, cab, getattr(it, "source", "") or "", landing))
  prev_hotel = None
  prev_area = None
  for b in it.stay_blocks:
    hotel = b.get("hotel")
    day = next((d for d in it.days if d.day_number == b.get("start_day")), None)
    choice = (choices or {}).get(b.get("index"))
    flown_or_rail = bool(choice and choice["mode"] in ("flight", "train") and choice["option"].get("departure_time"))
    if day and prev_area is not None and b.get("area") and flown_or_rail:
      # moving by plane or train: checkout, journey, arrival and check-in with the real times
      day.notes.append(transfer_card(choice["option"], prev_area, b["area"], prev_hotel, hotel))
    elif b.get("needs_hotel") and hotel and prev_hotel and hotel.get("name") != prev_hotel.get("name") and day:
      day.notes.append(hotel_change_card(prev_hotel, hotel, cab_estimate(_hotel_xy(prev_hotel), _hotel_xy(hotel))))
    if b.get("needs_hotel") and hotel:
      prev_hotel = hotel
    if b.get("area"):
      prev_area = b["area"]
  if ib:
    hotel = hotels_by_day.get(last.day_number) or hotels_by_day.get(last.day_number - 1)
    cab = cab_estimate(await _terminal_xy(ib, "leave"), _hotel_xy(hotel))
    last.notes.append(departure_card(ib, hotel, cab, getattr(it, "source", "") or "", landing))


@router.post("/finalize", response_model=ItineraryResponse, dependencies=[Depends(require_user)])
async def finalize_itinerary(req: FinalizeRequest):
  """Adds the hotel chosen for each stay, refreshes directions and the budget. No AI call, no new places."""
  it = req.itinerary
  choices = {c.block_index: c.hotel for c in req.stay_hotels}
  hotels_by_day: Dict[int, Dict[str, Any]] = {}
  chosen: List[Dict[str, Any]] = []
  budget_hotels: List[Dict[str, Any]] = []

  for b in it.stay_blocks:
    hotel = choices.get(b.get("index"))
    b["hotel"] = hotel
    if not b.get("needs_hotel"):
      continue
    label = f"{b.get('area') or 'Stay'} ({b.get('nights', 0)} night(s))"
    if hotel:
      chosen.append({**hotel, "block_index": b.get("index"), "area": b.get("area")})
      for d in range(int(b.get("start_day", 1)), int(b.get("end_day", 1)) + 1):
        hotels_by_day[d] = hotel
    budget_hotels.append({
        "index": b.get("index"), "label": label, "nights": b.get("nights", 0),
        "total_per_room": (hotel or {}).get("total_price"), "nightly": (hotel or {}).get("nightly_price"),
        "skipped": hotel is None and b.get("index") in choices,
    })

  it.selected_hotels = chosen or None
  it.selected_hotel = chosen[0] if chosen else None

  try:
    ctx = SimpleNamespace(transportation=req.transportation, transport_modes=req.transport_modes, selected_hotel=None,
                          selected_outbound_transport=it.selected_outbound_transport)
    enrich_itinerary(it, ctx, None, hotels_by_day or None)
  except Exception as exc:
    logger.warning(f"Could not refresh directions with hotels: {exc}")

  choices = _choice_by_stay(req)
  try:
    await _build_day_notes(it, hotels_by_day, choices)
  except Exception as exc:  # the cards are a bonus: never fail the itinerary
    logger.warning(f"Could not build arrival/departure notes: {exc}")

  def _price(d: Any) -> Optional[float]:
    return d.get("price") if isinstance(d, dict) else None

  # What the traveller chose for each long journey: kept on the transfer (shown later) and priced in the budget
  budget_transfers: List[Dict[str, Any]] = []
  for t in it.transfers:
    choice = choices.get(t.get("to_stay"))
    label = f"{t.get('from_area')} → {t.get('to_area')}"
    item = {"from_area": t.get("from_area"), "to_area": t.get("to_area"), "label": label,
            "distance_km": t.get("distance_km", 0), "cost_per_person": t.get("cost_per_person", 0)}
    if choice:
      opt = choice["option"]
      t["choice"] = {"mode": choice["mode"], **{k: opt.get(k) for k in (
          "operator", "number", "origin", "destination", "departure_time", "arrival_time", "duration_formatted", "price") if opt.get(k) is not None}}
      item["mode"] = choice["mode"]
      if choice["mode"] == "flight" and opt.get("price"):
        item["live_price_pp"] = float(opt["price"])
    budget_transfers.append(item)

  detail = build_budget(
      travelers=req.travelers_count, days=it.duration_days, per_day_per_person=float(req.budget_per_person_per_day),
      outbound_pp=_price(it.selected_outbound_transport), return_pp=_price(it.selected_return_transport),
      rooms=req.rooms, hotels=budget_hotels, transfers=budget_transfers,
  )
  stay_total = sum(l["total"] for l in detail["lines"] if l["key"].startswith("stay_"))
  it.cost_breakdown = {
      "outbound_transport_price": _price(it.selected_outbound_transport),
      "return_transport_price": _price(it.selected_return_transport),
      "hotel_total_price": stay_total or None,
      "food_and_activities_estimate": detail["estimate_total"],
      "overall_total_estimate": detail["grand_total"],
      "per_person_estimate": detail["per_person_total"],
      "currency": "INR",
      "hotel_selected": bool(chosen),
      "transport_selected": bool(it.selected_outbound_transport or it.selected_return_transport),
      "detail": detail,
  }
  it.estimated_budget_total = f"₹{detail['grand_total']:,} total estimate"
  return it
