"""Leg-by-leg directions between consecutive itinerary stops.

For every stop (sights, lunch, dinner, evening spots) this adds a `directions`
block describing how to get there FROM THE PREVIOUS STOP (not from the user's
current location): a compass heading, an approximate distance, a suggested
travel medium with an estimated time, and a Google Maps link whose origin is
that previous stop.

Distances are estimates (straight-line distance x a road factor), clearly
labelled as such. Turn-by-turn navigation is provided by the map link.
"""

import difflib
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

ROAD_FACTOR = 1.3
WALK_KMH = 4.5
VEHICLE_KMH = 18.0          # city traffic
HIGHWAY_KMH = 35.0          # longer trips between towns/outskirts
VEHICLE_OVERHEAD_MIN = 6

_COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def _norm(name: str) -> str:
  return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  r = 6371.0
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dp, dl = p2 - p1, math.radians(lon2 - lon1)
  a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
  return 2 * r * math.asin(math.sqrt(a))


def compass_heading(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
  y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
  x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(
      math.radians(lat1)
  ) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
  bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
  return _COMPASS[int((bearing + 22.5) // 45) % 8]


def suggest_mode(distance_km: float, preference: str) -> Tuple[str, str]:
  """Returns (label, google travelmode) for the leg, honouring the trip's local transport choice."""
  pref = (preference or "public").lower()
  if pref == "walking":
    return ("Walk", "walking")
  if pref == "driving":
    return ("Taxi / Auto-rickshaw", "driving") if distance_km > 0.6 else ("Walk", "walking")
  # public transit & walking
  if distance_km <= 1.2:
    return ("Walk", "walking")
  if distance_km <= 3.5:
    return ("Auto-rickshaw / e-rickshaw", "driving")
  return ("Local bus / metro or taxi", "transit")


def estimate_minutes(distance_km: float, mode_label: str) -> int:
  if mode_label == "Walk":
    return max(1, round(distance_km / WALK_KMH * 60))
  speed = HIGHWAY_KMH if distance_km > 10 else VEHICLE_KMH
  return max(3, round(distance_km / speed * 60 + VEHICLE_OVERHEAD_MIN))


class _Point:
  """A stop or starting point: name/address always, coordinates when known."""

  def __init__(self, name: str, address: Optional[str] = None,
               lat: Optional[float] = None, lon: Optional[float] = None):
    self.name, self.address, self.lat, self.lon = name, address, lat, lon

  @property
  def has_coords(self) -> bool:
    return self.lat is not None and self.lon is not None

  def maps_ref(self) -> str:
    if self.has_coords:
      return f"{self.lat},{self.lon}"
    return ", ".join(x for x in (self.name, self.address) if x)


def _lookup(name: str, address: Optional[str], places: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
  """Match an itinerary stop to a verified place (which carries coordinates)."""
  target = _norm(name)
  if not target:
    return None
  usable = [p for p in places if p.get("latitude") is not None and p.get("longitude") is not None]
  for p in usable:
    if _norm(p.get("name", "")) == target:
      return p
  for p in usable:
    cand = _norm(p.get("name", ""))
    if cand and len(min(cand, target, key=len)) >= 5 and (cand in target or target in cand):
      return p
  best, best_ratio = None, 0.0
  for p in usable:
    ratio = difflib.SequenceMatcher(None, target, _norm(p.get("name", ""))).ratio()
    if ratio > best_ratio:
      best, best_ratio = p, ratio
  return best if best_ratio >= 0.85 else None


def build_leg(origin: _Point, dest: _Point, preference: str) -> Dict[str, Any]:
  mode_label, travel_mode = ("Walk", "walking")
  distance_km: Optional[float] = None
  minutes: Optional[int] = None
  heading: Optional[str] = None

  if origin.has_coords and dest.has_coords:
    straight = haversine_km(origin.lat, origin.lon, dest.lat, dest.lon)
    distance_km = round(max(straight * ROAD_FACTOR, 0.05), 1)
    mode_label, travel_mode = suggest_mode(distance_km, preference)
    minutes = estimate_minutes(distance_km, mode_label)
    heading = compass_heading(origin.lat, origin.lon, dest.lat, dest.lon)
  else:
    mode_label, travel_mode = suggest_mode(2.0, preference)

  maps_url = (
      "https://www.google.com/maps/dir/?api=1"
      f"&origin={quote(origin.maps_ref())}"
      f"&destination={quote(dest.maps_ref())}"
      f"&travelmode={travel_mode}"
  )

  if distance_km is not None:
    summary = (
        f"From {origin.name}, head {heading} for about {distance_km} km. "
        f"Best way: {mode_label} (about {minutes} min)."
    )
  else:
    summary = (
        f"From {origin.name}. Exact distance is not available for this stop, "
        f"so open the map for the route ({mode_label} suggested)."
    )

  return {
      "from_name": origin.name,
      "distance_km": distance_km,
      "heading": heading,
      "mode": mode_label,
      "minutes": minutes,
      "summary": summary,
      "maps_url": maps_url,
      "estimate_note": "Distance and time are estimates; open the map for exact turn-by-turn directions.",
  }


def enrich_itinerary(response: Any, req: Any, verified_places: Optional[List[Dict[str, Any]]]) -> None:
  """Adds coordinates + `directions` to every stop of an ItineraryResponse, in place."""
  places = verified_places or []
  preference = getattr(req, "transportation", "public")

  hotel = getattr(req, "selected_hotel", None) or getattr(response, "selected_hotel", None)
  hotel_point: Optional[_Point] = None
  if isinstance(hotel, dict) and hotel.get("name"):
    hotel_point = _Point(hotel["name"], hotel.get("address"), hotel.get("latitude"), hotel.get("longitude"))

  arrival = getattr(req, "selected_outbound_transport", None) or {}
  arrival_name = arrival.get("destination") if isinstance(arrival, dict) else None
  arrival_point = _Point(arrival_name) if arrival_name else None

  last_stop: Optional[_Point] = None

  def attach(item: Any, origin: Optional[_Point]) -> _Point:
    name = getattr(item, "name", "") or ""
    address = getattr(item, "address", None)
    match = _lookup(name, address, places)
    lat = match.get("latitude") if match else None
    lon = match.get("longitude") if match else None
    if match:
      item.latitude, item.longitude = lat, lon
    point = _Point(name, address or (match.get("address") if match else None), lat, lon)
    if origin is not None:
      item.directions = build_leg(origin, point, preference)
    return point

  for day in response.days:
    if hotel_point is not None:
      origin = hotel_point
    elif day.day_number == 1 and arrival_point is not None:
      origin = arrival_point
    else:
      origin = last_stop

    sequence: List[Any] = []
    sequence += list(day.morning.places or [])
    sequence.append(day.food_stop_lunch)
    sequence += list(day.afternoon.places or [])
    sequence.append(day.food_stop_dinner)
    sequence += list(day.evening.places or [])

    for item in sequence:
      origin = attach(item, origin) if origin is not None else attach(item, None)
      last_stop = origin
