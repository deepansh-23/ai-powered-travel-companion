"""Flight service integrating SerpApi Google Flights engine (Section 6, 8, 31).
Performs independent one-way searches for outbound and return legs.
Deduplicates and normalizes best and other flight lists.
Never fabricates booking URLs or flight facts.
"""

import hashlib
import logging
import re
import time
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

# More of the world's busiest cities, so typing the plain city name just works (no code needed)
AIRPORT_MAP.update({
    "manchester": ["MAN"], "birmingham": ["BHX"], "edinburgh": ["EDI"], "glasgow": ["GLA"], "dublin": ["DUB"],
    "copenhagen": ["CPH"], "munich": ["MUC"], "munchen": ["MUC"], "frankfurt": ["FRA"], "berlin": ["BER"],
    "hamburg": ["HAM"], "cologne": ["CGN"], "dusseldorf": ["DUS"], "stuttgart": ["STR"], "amsterdam": ["AMS"],
    "brussels": ["BRU"], "madrid": ["MAD"], "barcelona": ["BCN"], "valencia": ["VLC"], "malaga": ["AGP"],
    "seville": ["SVQ"], "palma": ["PMI"], "lisbon": ["LIS"], "porto": ["OPO"], "rome": ["FCO"],
    "milan": ["MXP", "LIN"], "venice": ["VCE"], "florence": ["FLR"], "naples": ["NAP"], "bologna": ["BLQ"],
    "zurich": ["ZRH"], "geneva": ["GVA"], "vienna": ["VIE"], "prague": ["PRG"], "budapest": ["BUD"],
    "warsaw": ["WAW"], "krakow": ["KRK"], "bucharest": ["OTP"], "sofia": ["SOF"], "belgrade": ["BEG"],
    "zagreb": ["ZAG"], "split": ["SPU"], "dubrovnik": ["DBV"], "athens": ["ATH"], "istanbul": ["IST"],
    "stockholm": ["ARN"], "oslo": ["OSL"], "helsinki": ["HEL"], "reykjavik": ["KEF"], "nice": ["NCE"],
    "lyon": ["LYS"], "marseille": ["MRS"],
    "abu dhabi": ["AUH"], "sharjah": ["SHJ"], "muscat": ["MCT"], "riyadh": ["RUH"], "jeddah": ["JED"],
    "kuwait city": ["KWI"], "tel aviv": ["TLV"], "amman": ["AMM"],
    "kuala lumpur": ["KUL"], "hong kong": ["HKG"], "seoul": ["ICN", "GMP"], "osaka": ["KIX", "ITM"],
    "beijing": ["PEK", "PKX"], "shanghai": ["PVG", "SHA"], "guangzhou": ["CAN"], "taipei": ["TPE"],
    "manila": ["MNL"], "jakarta": ["CGK"], "bali": ["DPS"], "denpasar": ["DPS"], "hanoi": ["HAN"],
    "ho chi minh city": ["SGN"], "saigon": ["SGN"], "phnom penh": ["PNH"], "phuket": ["HKT"],
    "chiang mai": ["CNX"], "colombo": ["CMB"], "kathmandu": ["KTM"], "dhaka": ["DAC"], "male": ["MLE"],
    "karachi": ["KHI"], "lahore": ["LHE"], "islamabad": ["ISB"],
    "melbourne": ["MEL"], "brisbane": ["BNE"], "perth": ["PER"], "auckland": ["AKL"],
    "vancouver": ["YVR"], "montreal": ["YUL"], "chicago": ["ORD"], "boston": ["BOS"], "washington": ["IAD", "DCA"],
    "miami": ["MIA"], "seattle": ["SEA"], "las vegas": ["LAS"], "atlanta": ["ATL"], "dallas": ["DFW"],
    "houston": ["IAH"], "orlando": ["MCO"], "philadelphia": ["PHL"], "san diego": ["SAN"], "denver": ["DEN"],
    "mexico city": ["MEX"], "sao paulo": ["GRU"], "rio de janeiro": ["GIG"], "buenos aires": ["EZE"],
    "lima": ["LIM"], "bogota": ["BOG"], "santiago": ["SCL"],
    "cairo": ["CAI"], "johannesburg": ["JNB"], "cape town": ["CPT"], "nairobi": ["NBO"], "addis ababa": ["ADD"],
    "casablanca": ["CMN"], "marrakech": ["RAK"], "mauritius": ["MRU"],
})

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


# ---------------------------------------------------------------- live airport lookup
_AIRPORT_LOOKUP_TTL = 24 * 3600.0
_airport_cache: Dict[str, Tuple[float, List[str], List[str]]] = {}
MAX_AIRPORTS_PER_CITY = 3


def pick_airports_from_autocomplete(data: Dict[str, Any], query: str) -> Tuple[List[str], List[str]]:
  """Reads a SerpApi Google Flights Autocomplete response.

  Returns (airport_codes, alternative_names).
  A city is accepted only when its name (text before the first comma) equals what the user typed,
  so a city is never guessed. When several cities share a name ("Manchester" in England and in
  New Hampshire) the words the user added after the comma ("England", "United Kingdom") pick one.
  Other cities that were found are returned as 'did you mean' alternatives.
  """
  wanted = _city_key(query)
  qualifiers = [q.strip().lower() for q in query.split(",")[1:] if q.strip()]
  best: Optional[Tuple[int, List[str]]] = None
  alternatives: List[str] = []
  for idx, sug in enumerate(data.get("suggestions") or []):
    if not isinstance(sug, dict):
      continue
    name = str(sug.get("name") or "")
    airports = [a for a in (sug.get("airports") or []) if isinstance(a, dict) and str(a.get("id") or "").strip()]
    codes = [str(a["id"]).strip().upper() for a in airports]
    if not codes and sug.get("type") == "airport":  # an airport listed on its own
      code = str(sug.get("id") or "").strip().upper()
      if len(code) == 3 and code.isalpha() and _city_key(name).startswith(wanted):
        codes = [code]
    if not codes:
      continue
    is_exact = _city_key(name) == wanted or (sug.get("type") == "airport" and _city_key(name).startswith(wanted))
    if is_exact:
      text = f"{name} {sug.get('description') or ''}".lower()
      score = 100 - idx + 10 * sum(1 for q in qualifiers if q in text)
      if best is None or score > best[0]:
        best = (score, codes[:MAX_AIRPORTS_PER_CITY])
    elif name and name not in alternatives:
      alternatives.append(name)
  return (best[1] if best else []), alternatives[:4]


async def _lookup_codes_live(query: str) -> Tuple[List[str], List[str]]:
  """One cached Google Flights autocomplete lookup. Only real answers are cached, never failures."""
  key = query.strip().lower()
  cached = _airport_cache.get(key)
  if cached and time.time() - cached[0] < _AIRPORT_LOOKUP_TTL:
    return cached[1], cached[2]
  data = await serpapi_client.search({"engine": "google_flights_autocomplete", "q": query.strip(), "hl": "en"})
  codes, alternatives = pick_airports_from_autocomplete(data, query)
  if data.get("suggestions"):
    _airport_cache[key] = (time.time(), codes, alternatives)
  if not codes:
    logger.info("Airport lookup for %r found no exact city; suggestions: %s", query,
                [s.get("name") for s in (data.get("suggestions") or []) if isinstance(s, dict)][:6])
  return codes, alternatives


async def resolve_airports(city_name: str) -> Tuple[List[str], Optional[str]]:
  """Airport codes for ANY city typed by name: built-in list, then Google Flights autocomplete,
  then (for typos like 'Manchaster') the spelling Geoapify recognises. Never needs the IATA code."""
  codes, notice = resolve_city_to_airports(city_name)
  if codes:
    return codes, None
  key = _city_key(city_name)
  if key in NO_AIRPORT_CITIES or not key:
    return codes, notice  # explicit "no airport" answer

  alternatives: List[str] = []
  try:
    live, alternatives = await _lookup_codes_live(city_name)
    if live:
      return live, None
  except Exception as exc:  # no key, quota, network...
    logger.info(f"Airport lookup unavailable for '{city_name}': {exc}")
    return [], notice

  # Spelling / wording the autocomplete did not recognise: ask for the canonical city name once
  try:
    from app.services.place_suggest_service import place_suggest_service
    suggestions, _ = await place_suggest_service.suggest(city_name, 5)
    for sug in suggestions:
      if sug["kind"] != "city":
        continue
      canonical = sug["name"]
      if _city_key(canonical) == key:
        continue
      qualified = ", ".join(x for x in (canonical, sug.get("state"), sug.get("country")) if x)
      for attempt in (canonical, qualified):
        mapped, _n = resolve_city_to_airports(attempt)
        if mapped:
          return mapped, None
        live, more = await _lookup_codes_live(attempt)
        if live:
          return live, None
        alternatives += [m for m in more if m not in alternatives]
      break
  except Exception as exc:
    logger.info(f"Spelling check for '{city_name}' failed: {exc}")

  hint = f" Did you mean: {', '.join(alternatives[:4])}?" if alternatives else ""
  return [], f"No airport found for '{city_name.strip()}'.{hint}"


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
    origin_airports, orig_notice = await resolve_airports(origin_city)
    dest_airports, dest_notice = await resolve_airports(dest_city)

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

    # ONE search per leg, using the best-matching airport pair (the first airport that the existing selection
    # logic returns for each city). Other airports are never searched automatically, to save SerpApi credits.
    pairs = [(d, a) for d in origin_airports for a in dest_airports if d != a][:1]
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
