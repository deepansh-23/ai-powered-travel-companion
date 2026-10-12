"""Flight service integrating SerpApi Google Flights engine (Section 6, 8, 31).
Performs independent one-way searches for outbound and return legs.
Deduplicates and normalizes best and other flight lists.
Never fabricates booking URLs or flight facts.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.transport import TransportOption
from app.services.serpapi_client import serpapi_client

logger = logging.getLogger(__name__)

# Curated IATA airport mapping for major domestic and international hubs
# If a city is not here, check if it's already an IATA 3-letter code.
# Cities with no direct commercial airport are explicitly mapped or recognized.
AIRPORT_MAP: Dict[str, List[str]] = {
    # India
    "delhi": ["DEL"],
    "new delhi": ["DEL"],
    "mumbai": ["BOM"],
    "bombay": ["BOM"],
    "amritsar": ["ATQ"],
    "goa": ["GOI", "GOX"],
    "bangalore": ["BLR"],
    "bengaluru": ["BLR"],
    "kolkata": ["CCU"],
    "calcutta": ["CCU"],
    "chennai": ["MAA"],
    "madras": ["MAA"],
    "hyderabad": ["HYD"],
    "jaipur": ["JAI"],
    "ahmedabad": ["AMD"],
    "pune": ["PNQ"],
    "varanasi": ["VNS"],
    "lucknow": ["LKO"],
    "chandigarh": ["IXC"],
    "srinagar": ["SXR"],
    "kochi": ["COK"],
    "cochin": ["COK"],
    "thiruvananthapuram": ["TRV"],
    "trivandrum": ["TRV"],
    "guwahati": ["GAU"],
    "bhubaneswar": ["BBI"],
    "patna": ["PAT"],
    "indore": ["IDR"],
    "bhopal": ["BHO"],
    "nagpur": ["NAG"],
    "coimbatore": ["CJB"],
    "visakhapatnam": ["VTZ"],
    "vizag": ["VTZ"],
    "mangalore": ["IXE"],
    "dehradun": ["DED"],
    "udaipur": ["UDR"],
    "jodhpur": ["JDH"],
    "jammu": ["IXJ"],
    "bagdogra": ["IXB"],
    "darjeeling": ["IXB"],
    "port blair": ["IXZ"],
    # International hubs
    "dubai": ["DXB"],
    "london": ["LHR", "LGW"],
    "new york": ["JFK", "EWR"],
    "paris": ["CDG"],
    "singapore": ["SIN"],
    "bangkok": ["BKK"],
    "tokyo": ["HND", "NRT"],
    "doha": ["DOH"],
    "sydney": ["SYD"],
    "san francisco": ["SFO"],
    "toronto": ["YYZ"],
    "los angeles": ["LAX"],
}

# Cities explicitly known to NOT have an operational commercial airport
NO_AIRPORT_CITIES = {
    "rishikesh",
    "haridwar",
    "manali",
    "kasol",
    "mussoorie",
    "nainital",
    "ooty",
    "kodaikanal",
    "munnar",
    "mathura",
    "vrindavan",
    "alwar",
    "pushkar",
    "alleppey",
    "hampi",
}


def _city_key(city_name: str) -> str:
  """Normalizes 'Amritsar, Punjab, India' -> 'amritsar' (text before first comma)."""
  return re.sub(r"\s+", " ", city_name.split(",")[0].strip().lower())


def resolve_city_to_airports(city_name: str) -> Tuple[List[str], Optional[str]]:
  """Resolves city to a list of IATA airport codes or returns a clear notice.

  Exact matching only: a city is never guessed from a partial name.
  Returns (codes_list, notice_message).
  """
  clean = city_name.strip()
  if len(clean) == 3 and clean.isalpha() and clean.isupper():
    return [clean], None

  key = _city_key(clean)

  if key in NO_AIRPORT_CITIES:
    return (
        [],
        (
            f"No commercial airport serves '{clean}' directly. Consider"
            " railway travel instead."
        ),
    )

  if key in AIRPORT_MAP:
    return AIRPORT_MAP[key], None

  return (
      [],
      (
          f"Could not verify a commercial airport code for '{clean}'. Train"
          " travel is recommended."
      ),
  )


class FlightService:

  def parse_serpapi_flights(
      self, data: Dict[str, Any], currency: str = "INR"
  ) -> List[TransportOption]:
    """Normalizes SerpApi Google Flights response into TransportOption items.

    Merges 'best_flights' and 'other_flights' and deduplicates.
    """
    provider_search_url = (data.get("search_metadata") or {}).get("google_flights_url")
    insights = data.get("price_insights") or {}
    insight_text = None
    if insights.get("price_level"):
      insight_text = f"Price is {insights['price_level']} for this route"
      rng = insights.get("typical_price_range")
      if isinstance(rng, list) and len(rng) == 2:
        insight_text += f" (typical {rng[0]}-{rng[1]})"
    raw_best = data.get("best_flights", [])
    raw_other = data.get("other_flights", [])
    all_raw = raw_best + raw_other

    options: List[TransportOption] = []
    seen_keys = set()

    for item in all_raw:
      flights = item.get("flights", [])
      if not flights:
        continue

      first_leg = flights[0]
      last_leg = flights[-1]

      airline = first_leg.get("airline", "Commercial Airline")
      flight_num = first_leg.get("flight_number", "")
      origin_info = first_leg.get("departure_airport", {})
      dest_info = last_leg.get("arrival_airport", {})

      origin_code = origin_info.get("id") or origin_info.get("name", "Origin")
      dest_code = dest_info.get("id") or dest_info.get("name", "Dest")

      dep_time = origin_info.get("time", "")
      arr_time = dest_info.get("time", "")

      duration_minutes = item.get("total_duration", 0)
      if duration_minutes <= 0:
        duration_minutes = sum(f.get("duration", 0) for f in flights)

      stops_count = len(flights) - 1
      layover_parts = []
      layovers = item.get("layovers", [])
      for lo in layovers:
        lo_code = lo.get("id")
        lo_name = lo.get("name")
        lo_display = f"{lo_name} ({lo_code})" if lo_code and lo_name else (lo_name or lo_code or "Layover")
        lo_dur = lo.get("duration", 0)
        layover_parts.append(f"{lo_display} ({lo_dur}m)")
      layover_str = ", ".join(layover_parts) if layover_parts else None


      # Price extraction
      price_val = item.get("price")
      if isinstance(price_val, str):
        # Extract digits from e.g. "₹5,420"
        import re

        digits = re.sub(r"[^\d.]", "", price_val)
        try:
          price_val = float(digits) if digits else None
        except Exception:
          price_val = None

      # Provider booking link if present in booking_options or link
      booking_url = None
      booking_options = item.get("booking_options", [])
      if booking_options and isinstance(booking_options, list):
        for b_opt in booking_options:
          if b_opt.get("book_with") or b_opt.get("link"):
            booking_url = b_opt.get("link")
            break
      if not booking_url:
        booking_url = item.get("link")
      if not booking_url:
        # Provider-supplied Google Flights results page (never constructed here)
        booking_url = provider_search_url or None

      # Deduplication key
      dedup_key = (
          f"{airline}_{flight_num}_{origin_code}_{dest_code}_{dep_time}_{price_val}"
      )
      if dedup_key in seen_keys:
        continue
      seen_keys.add(dedup_key)

      dur_h = duration_minutes // 60
      dur_m = duration_minutes % 60
      duration_formatted = f"{dur_h}h {dur_m}m" if dur_h > 0 else f"{dur_m}m"

      # Cabin class
      cabin = first_leg.get("travel_class", "Economy")

      flight_id = f"flt_{hashlib.sha1(dedup_key.encode()).hexdigest()[:10]}"

      option = TransportOption(
          id=flight_id,
          mode="flight",
          provider="serpapi_google_flights",
          operator=airline,
          number=flight_num,
          origin=f"{origin_code} ({origin_info.get('name', origin_code)})",
          destination=f"{dest_code} ({dest_info.get('name', dest_code)})",
          departure_time=dep_time,
          arrival_time=arr_time,
          duration_minutes=duration_minutes,
          duration_formatted=duration_formatted,
          stops=stops_count,
          layover_details=layover_str,
          price=price_val,
          currency=currency,
          cabin_or_class=cabin,
          booking_url=booking_url,
          price_insight=insight_text,
          raw_provider_data={
              "booking_token": item.get("booking_token"),
              "airline_logo": first_leg.get("airline_logo"),
              "airplane": first_leg.get("airplane"),
              "legroom": first_leg.get("legroom"),
              "extensions": item.get("extensions", []),
          },
      )
      options.append(option)

    return options

  async def search_flights(
      self,
      origin_city: str,
      dest_city: str,
      date_str: str,
      adults: int = 1,
      currency: str = "INR",
  ) -> Tuple[List[TransportOption], Optional[str]]:
    """Performs one-way Google Flights search for a specific route and date.

    Returns (options, notice).
    """
    origin_airports, orig_notice = resolve_city_to_airports(origin_city)
    dest_airports, dest_notice = resolve_city_to_airports(dest_city)

    if orig_notice:
      return [], orig_notice
    if dest_notice:
      return [], dest_notice
    if not origin_airports:
      return (
          [],
          (
              f"Could not resolve an airport for origin '{origin_city}'. Use"
              " trains instead."
          ),
      )
    if not dest_airports:
      return (
          [],
          (
              f"Could not resolve an airport for destination '{dest_city}'. Use"
              " trains instead."
          ),
      )

    # Search every airport pair (capped to protect SerpApi credits) and merge.
    pairs = [(d, a) for d in origin_airports for a in dest_airports if d != a][:4]
    if not pairs:
      return [], f"Origin and destination resolve to the same airport ({origin_city})."

    merged: List[TransportOption] = []
    seen_ids = set()
    last_error: Optional[Exception] = None
    successes = 0
    for dep_code, arr_code in pairs:
      params = {
          "engine": "google_flights",
          "departure_id": dep_code,
          "arrival_id": arr_code,
          "outbound_date": date_str,
          "adults": adults,
          "currency": currency,
          "hl": "en",
          "gl": "in",
          "type": "2",  # One-way search
      }
      try:
        data = await serpapi_client.search(params)
        successes += 1
        for opt in self.parse_serpapi_flights(data, currency=currency):
          if opt.id not in seen_ids:
            seen_ids.add(opt.id)
            raw = dict(opt.raw_provider_data or {})
            raw["search_params"] = {
                "departure_id": dep_code,
                "arrival_id": arr_code,
                "outbound_date": date_str,
                "adults": adults,
                "currency": currency,
            }
            opt.raw_provider_data = raw
            merged.append(opt)
      except Exception as exc:
        last_error = exc
        logger.warning(
            f"Google Flights search failed for {dep_code}->{arr_code} on"
            f" {date_str}: {exc}"
        )

    if successes == 0 and last_error is not None:
      raise last_error
    return merged, None

  async def get_booking_options(
      self, booking_token: str, search_params: Dict[str, Any]
  ) -> List[Dict[str, Any]]:
    """Fetches provider booking options for a selected one-way flight.

    Repeats the original search parameters plus booking_token (SerpApi's
    documented flow). Returns provider-supplied options only: each has
    book_with, price and either a direct url or a booking_request
    (url + post_data) that the browser must POST. Nothing is constructed.
    """
    if not booking_token:
      return []
    params = dict(search_params)
    params.update({
        "engine": "google_flights",
        "hl": "en",
        "gl": "in",
        "type": "2",
        "booking_token": booking_token,
    })
    data = await serpapi_client.search(params)
    options: List[Dict[str, Any]] = []
    for entry in data.get("booking_options", []) or []:
      block = entry.get("together") or entry.get("departing") or entry
      if not isinstance(block, dict):
        continue
      req = block.get("booking_request") or {}
      options.append({
          "book_with": block.get("book_with"),
          "price": block.get("price"),
          "option_title": block.get("option_title"),
          "url": block.get("link") or req.get("url"),
          "post_data": req.get("post_data"),
      })
    return [o for o in options if o.get("url")]


flight_service = FlightService()
