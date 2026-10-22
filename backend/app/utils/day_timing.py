"""Plain-language timing for the first day, the last day and hotel changes (pure Python, easy to test).

Every number here is computed from the traveller's real flight or train times plus clearly
labelled estimates (airport exit time, cab time from distance). The AI never invents them.

Assumptions, all shown to the traveller as such:
  * leave the airport about 45 minutes after landing (about 20 minutes after a train arrives)
  * hotel check-in usually opens at 14:00, check-out is by 11:00
  * be at the airport 2 hours before a flight, at the station 1 hour before a train
  * cab time = road distance (straight line x 1.3) at about 28 km/h, plus 8 minutes
"""

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

AIRPORT_EXIT_MIN = 45
STATION_EXIT_MIN = 20
SETTLE_IN_MIN = 90               # rest time after check-in before sightseeing (see settle_minutes)
SETTLE_BEFORE_CHECKIN_MIN = 60   # reached the hotel before check-in: leave bags, freshen up, then go
EVENING_END = "22:00"            # sightseeing on arrival / transfer days wraps up by this time
DINNER_ONLY_FROM = "20:30"       # starting later than this: just dinner near the hotel
CHECK_IN_TIME = "14:00"
CHECK_OUT_TIME = "11:00"
FLIGHT_BUFFER_MIN = 120
TRAIN_BUFFER_MIN = 60
DEFAULT_CAB_MIN = 40            # when the airport or station position is unknown
ROAD_FACTOR = 1.3
CAB_KMH = 28.0
CAB_OVERHEAD_MIN = 8

_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")


def parse_dt(value: Any) -> Optional[datetime]:
  """'2026-11-04 10:15' (or ISO) -> datetime. Anything else -> None (the plan then skips clock times)."""
  text = str(value or "").strip()
  for fmt in _FORMATS:
    try:
      return datetime.strptime(text[:19] if "T" in text and len(text) > 19 else text, fmt)
    except ValueError:
      continue
  return None


def hhmm(dt: datetime) -> str:
  return dt.strftime("%H:%M")


def settle_minutes(arrive_hotel: datetime) -> int:
  """1 to 1.5 hours between reaching the hotel and the first stop: freshen up, eat, rest."""
  return SETTLE_IN_MIN if hhmm(arrive_hotel) >= CHECK_IN_TIME else SETTLE_BEFORE_CHECKIN_MIN


def round_up_30(dt: datetime) -> datetime:
  extra = (-(dt.minute % 30)) % 30
  return (dt + timedelta(minutes=extra)).replace(second=0, microsecond=0)


def haversine_km(a: tuple, b: tuple) -> float:
  (lat1, lon1), (lat2, lon2) = a, b
  p1, p2 = math.radians(lat1), math.radians(lat2)
  h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
  return 2 * 6371.0 * math.asin(math.sqrt(h))


def cab_estimate(a: Optional[tuple], b: Optional[tuple]) -> Dict[str, Any]:
  """{'minutes', 'km', 'known'}: from two (lat, lon) points, or the typical default when one is missing."""
  if not a or not b:
    return {"minutes": DEFAULT_CAB_MIN, "km": None, "known": False}
  km = haversine_km(a, b) * ROAD_FACTOR
  return {"minutes": max(10, int(round(km / CAB_KMH * 60 + CAB_OVERHEAD_MIN))), "km": round(km, 1), "known": True}


def _is_flight(leg: Dict[str, Any]) -> bool:
  return str(leg.get("mode") or "").lower() == "flight"


def _duration_text(leg: Dict[str, Any]) -> str:
  return str(leg.get("duration_formatted") or "").strip()


def _operator(leg: Dict[str, Any]) -> str:
  return " ".join(x for x in (str(leg.get("operator") or "").replace("Indian Railways (", "").rstrip(")"),
                              str(leg.get("number") or "")) if x).strip() or "your booking"


def _short_place(text: Any) -> str:
  """'GOI (Dabolim Airport)' -> 'Dabolim Airport'; 'MAO Station' stays as is."""
  t = str(text or "").strip()
  if "(" in t and t.endswith(")"):
    return t[t.index("(") + 1:-1]
  return t


# ---------------------------------------------------------------- windows for the AI
def day_windows(outbound: Optional[Dict[str, Any]], inbound: Optional[Dict[str, Any]], days: int,
                first_cab_min: int = DEFAULT_CAB_MIN, last_cab_min: int = DEFAULT_CAB_MIN) -> Dict[str, Optional[str]]:
  """When sightseeing may start on day 1 and must end on the last day ('HH:MM' or None for 'no limit')."""
  start: Optional[str] = None
  end: Optional[str] = None
  arr = parse_dt((outbound or {}).get("arrival_time"))
  if arr:
    exit_min = AIRPORT_EXIT_MIN if _is_flight(outbound) else STATION_EXIT_MIN
    at_hotel = arr + timedelta(minutes=exit_min + first_cab_min)
    ready = round_up_30(at_hotel + timedelta(minutes=settle_minutes(at_hotel)))
    start = hhmm(ready) if ready.date() == arr.date() else "23:59"
  dep = parse_dt((inbound or {}).get("departure_time"))
  if dep:
    buffer_min = FLIGHT_BUFFER_MIN if _is_flight(inbound) else TRAIN_BUFFER_MIN
    finish = dep - timedelta(minutes=buffer_min + last_cab_min + 30)  # 30 min to check out and set off
    end = hhmm(finish) if finish.date() == dep.date() else "00:00"
  return {"start": start, "end": end}


def window_prompt_lines(windows: Dict[str, Optional[str]], days: int) -> List[str]:
  lines: List[str] = []
  st, e = windows.get("start"), windows.get("end")
  if st:
    if st >= DINNER_ONLY_FROM:
      lines.append("- DAY 1: the traveller arrives late. Leave morning, lunch and afternoon without places. Plan only a "
                   "relaxed dinner near the hotel (food_stop_dinner) and optionally a very short walk. No other sightseeing.")
    else:
      lunch = ("Include a lunch stop only if it is before 14:30; otherwise skip lunch (reuse a light cafe stop). "
               if st > "13:30" else "")
      lines.append(
          f"- DAY 1: the traveller lands and rests at the hotel first, so sightseeing may START at {st} at the earliest "
          f"(about 1 to 1.5 hours after reaching the hotel). Still plan Day 1 properly: leave every time slot before {st} "
          f"empty, then plan 1 to 3 places that fit between {st} and {EVENING_END} (fewer places the later it starts), "
          f"with a dinner stop. {lunch}Never schedule anything before {st} and wrap up by {EVENING_END}. "
          "Pick places close to each other and to the hotel, and make time_window values respect this.")
  else:
    lines.append("- DAY 1: no arrival time is known, so a normal day starting around 10:00 is fine.")
  if e and days > 1:
    lines.append(f"- LAST DAY (Day {days}): all sightseeing must be FINISHED by {e}. Keep that day short.")
  lines.append("- Do NOT write about the flight or train, the airport or station, the cab to the hotel, check-in or "
               "check-out. That is shown separately. Start each plan from its first place.")
  return lines


# ---------------------------------------------------------------- cards shown on the itinerary
def arrival_card(outbound: Dict[str, Any], hotel: Optional[Dict[str, Any]], cab: Dict[str, Any],
                 source: str = "", destination: str = "") -> Dict[str, Any]:
  arr = parse_dt(outbound.get("arrival_time"))
  dep = parse_dt(outbound.get("departure_time"))
  flight = _is_flight(outbound)
  verb = "fly" if flight else "travel"
  route = f"{source} → {destination}".strip(" →") if (source or destination) else ""
  lines: List[str] = []
  head = f"Today you {verb}" + (f" {route}" if route else "") + f" with {_operator(outbound)}"
  if dep and arr:
    dur = _duration_text(outbound)
    head += f": leaves {hhmm(dep)}, arrives {hhmm(arr)}" + (f" (about {dur} on the way)" if dur else "")
  lines.append(head + ".")
  if arr:
    exit_min = AIRPORT_EXIT_MIN if flight else STATION_EXIT_MIN
    out_at = arr + timedelta(minutes=exit_min)
    lines.append(f"After you arrive, allow about {exit_min} minutes to {'collect bags and leave the airport' if flight else 'leave the station'}"
                 f" (around {hhmm(out_at)}).")
    where = f"to {hotel['name']}" if hotel and hotel.get("name") else "to your hotel"
    est = f"about {cab['minutes']} min" + (f", {cab['km']} km" if cab.get("km") else "")
    lines.append(f"🚕 Cab {where}: {est} (estimate" + ("" if cab.get("known") else ", typical time; distance not known") + ").")
    arrive_hotel = out_at + timedelta(minutes=cab["minutes"])
    if arrive_hotel.strftime("%H:%M") < CHECK_IN_TIME:
      lines.append(f"🏨 You reach the hotel around {hhmm(arrive_hotel)}. Check-in is usually from {CHECK_IN_TIME}, so leave your bags "
                   "at the desk and start exploring. Early check-in is not guaranteed.")
    else:
      lines.append(f"🏨 You reach the hotel around {hhmm(arrive_hotel)}, after standard check-in time ({CHECK_IN_TIME}). Check in and freshen up.")
    ready = round_up_30(arrive_hotel + timedelta(minutes=settle_minutes(arrive_hotel)))
    if ready.date() == arr.date():
      lines.append(f"Rest and freshen up first. Your first stop is around {hhmm(ready)}.")
  return {"type": "arrival", "title": "Getting there", "icon": "✈️" if flight else "🚆", "lines": lines}


def departure_card(inbound: Dict[str, Any], hotel: Optional[Dict[str, Any]], cab: Dict[str, Any],
                   source: str = "", destination: str = "") -> Dict[str, Any]:
  dep = parse_dt(inbound.get("departure_time"))
  arr = parse_dt(inbound.get("arrival_time"))
  flight = _is_flight(inbound)
  lines: List[str] = [f"🏨 Check out by {CHECK_OUT_TIME}" + (f" from {hotel['name']}" if hotel and hotel.get("name") else "") + "."]
  if dep:
    buffer_min = FLIGHT_BUFFER_MIN if flight else TRAIN_BUFFER_MIN
    be_there = dep - timedelta(minutes=buffer_min)
    leave_by = be_there - timedelta(minutes=cab["minutes"])
    est = f"about {cab['minutes']} min" + (f", {cab['km']} km" if cab.get("km") else "")
    lines.append(f"🚕 Cab to the {'airport' if flight else 'station'}: {est} (estimate). Leave the hotel by {hhmm(leave_by)}.")
    lines.append(f"Be at the {'airport' if flight else 'station'} by {hhmm(be_there)} "
                 f"({'2 hours' if flight else '1 hour'} before departure).")
    route = f"{destination} → {source}".strip(" →") if (source or destination) else ""
    tail = f"{'✈️' if flight else '🚆'} {_operator(inbound)}{(' · ' + route) if route else ''}: leaves {hhmm(dep)}"
    if arr:
      tail += f", arrives {hhmm(arr)}"
    dur = _duration_text(inbound)
    if dur:
      tail += f" (about {dur} on the way)"
    lines.append(tail + ".")
  return {"type": "departure", "title": "Heading home", "icon": "🧳", "lines": lines}


def hotel_change_card(from_hotel: Dict[str, Any], to_hotel: Dict[str, Any], cab: Dict[str, Any]) -> Dict[str, Any]:
  a, b = from_hotel.get("name") or "your last hotel", to_hotel.get("name") or "your next hotel"
  est = f"about {cab['minutes']} min" + (f" ({cab['km']} km)" if cab.get("km") else "")
  lines = [
      f"Check out of {a} by {CHECK_OUT_TIME}.",
      f"🚕 Travel to {b}: {est} by cab (estimate)." + ("" if cab.get("known") else " Exact distance not known."),
      f"🏨 Check in at {b} from {CHECK_IN_TIME}. If you arrive earlier, leave your bags and carry on exploring.",
  ]
  return {"type": "hotel_change", "title": "Changing hotel today", "icon": "🔁", "lines": lines,
          "from_hotel": a, "to_hotel": b, "distance_km": cab.get("km"), "minutes": cab["minutes"]}


def transfer_card(option: Dict[str, Any], from_area: str, to_area: str, from_hotel: Optional[Dict[str, Any]],
                  to_hotel: Optional[Dict[str, Any]]) -> Dict[str, Any]:
  """The day the traveller moves between two places by plane or train: checkout, journey, arrival, check-in."""
  dep = parse_dt(option.get("departure_time"))
  arr = parse_dt(option.get("arrival_time"))
  flight = _is_flight(option)
  noun = "airport" if flight else "station"
  lines: List[str] = [f"Check out of {from_hotel['name']} before you leave." if from_hotel and from_hotel.get("name")
                      else f"Check out of your hotel in {from_area} before you leave."]
  head = f"{'✈️' if flight else '🚆'} {_operator(option)}: {_short_place(option.get('origin'))} → {_short_place(option.get('destination'))}"
  if dep and arr:
    head += f", leaves {hhmm(dep)}, arrives {hhmm(arr)}"
    dur = _duration_text(option)
    if dur:
      head += f" (about {dur} on the way)"
    buffer_min = FLIGHT_BUFFER_MIN if flight else TRAIN_BUFFER_MIN
    be_there = dep - timedelta(minutes=buffer_min)
    leave_by = be_there - timedelta(minutes=DEFAULT_CAB_MIN)
    lines.append(f"🚕 Cab to the {noun}: about {DEFAULT_CAB_MIN} min (typical time, estimate). Leave your hotel by {hhmm(leave_by)} "
                 f"and be at the {noun} by {hhmm(be_there)} ({'2 hours' if flight else '1 hour'} before departure).")
  lines.append(head + ".")
  if arr:
    exit_min = AIRPORT_EXIT_MIN if flight else STATION_EXIT_MIN
    reach = arr + timedelta(minutes=exit_min + DEFAULT_CAB_MIN)
    where = f"to {to_hotel['name']}" if to_hotel and to_hotel.get("name") else f"to your hotel in {to_area}"
    lines.append(f"After you arrive, allow about {exit_min} min to leave the {noun}, then a cab {where} "
                 f"(about {DEFAULT_CAB_MIN} min, estimate). You reach the hotel around {hhmm(reach)}.")
    lines.append(f"🏨 Check-in is usually from {CHECK_IN_TIME}. If you arrive earlier, leave your bags and start exploring.")
  return {"type": "transfer", "title": f"Travelling to {to_area}", "icon": "✈️" if flight else "🚆", "lines": lines,
          "mode": "flight" if flight else "train", "from_area": from_area, "to_area": to_area}


# ---------------------------------------------------------------- fitting a day to arrival / departure times
import re as _re

_CLOCK = _re.compile(r"(\d{1,2})[:.](\d{2})\s*([AaPp][Mm])?")


def parse_clock(text: Any) -> List[int]:
  """All clock times in a phrase like '08:30 AM – 12:00 PM' as minutes after midnight ([] when none)."""
  out: List[int] = []
  for h, m, ap in _CLOCK.findall(str(text or "")):
    hh, mm = int(h), int(m)
    if ap:
      ap = ap.lower()
      if ap == "pm" and hh < 12:
        hh += 12
      if ap == "am" and hh == 12:
        hh = 0
    if 0 <= hh < 24 and 0 <= mm < 60:
      out.append(hh * 60 + mm)
  return out


def _fmt_min(total: int) -> str:
  total = max(0, min(23 * 60 + 59, total))
  return f"{total // 60:02d}:{total % 60:02d}"


def _hhmm_to_min(value: Optional[str]) -> Optional[int]:
  if not value:
    return None
  h, m = value.split(":")
  return int(h) * 60 + int(m)


def ready_time_after_arrival(option: Optional[Dict[str, Any]], cab_minutes: int = DEFAULT_CAB_MIN) -> Optional[str]:
  """'HH:MM' when sightseeing can start after landing/arriving, rest included; None when unknown."""
  return day_windows(option, None, 1, first_cab_min=cab_minutes)["start"]


def _clear_segment(seg: Any, why: str) -> None:
  seg.places = []
  seg.time_window = ""
  seg.title = "Travel and settling in"
  seg.description = why
  seg.transport_note = None


def fit_day_to_window(day: Any, start_hhmm: Optional[str] = None, end_hhmm: Optional[str] = None) -> bool:
  """Removes plans that fall outside the hours the traveller is really free (arrival / departure days).

  Works on the day's morning, afternoon and evening segments using their time_window text. Returns True when
  anything changed. Lunch and dinner are marked `skipped` when their time has passed or cannot be reached.
  """
  s_min, e_min = _hhmm_to_min(start_hhmm), _hhmm_to_min(end_hhmm)
  if s_min is None and e_min is None:
    return False
  changed = False
  why_start = "You are still travelling or settling in during this part of the day."
  why_end = "This part of the day is left free so you can get to your journey home on time."
  for seg in (day.morning, day.afternoon, day.evening):
    times = parse_clock(seg.time_window)
    if len(times) < 2 or not (seg.places or seg.title):
      continue
    seg_start, seg_end = times[0], times[1]
    if seg_end <= seg_start:            # "10:00 PM – 12:00 AM" style: treat as ending the same night
      seg_end = 24 * 60 - 1
    if s_min is not None and seg_end <= s_min:
      _clear_segment(seg, why_start)
      changed = True
    elif s_min is not None and seg_start < s_min < seg_end:
      seg.time_window = f"{_fmt_min(s_min)} – {_fmt_min(seg_end)}"
      changed = True
    if e_min is not None and seg_start >= e_min and seg.places:
      _clear_segment(seg, why_end)
      changed = True
  evening_limit = _hhmm_to_min(EVENING_END)
  if s_min is not None and evening_limit is not None:
    ev = parse_clock(day.evening.time_window)
    if len(ev) >= 2 and ev[1] > evening_limit and ev[1] < 24 * 60 - 1 and day.evening.places:
      day.evening.time_window = f"{_fmt_min(ev[0])} – {_fmt_min(evening_limit)}"
      changed = True
  if s_min is not None:
    if s_min > 14 * 60 + 30 and not getattr(day.food_stop_lunch, "skipped", False):
      day.food_stop_lunch.skipped = True
      changed = True
    if s_min >= (_hhmm_to_min(DINNER_ONLY_FROM) or 0):
      for seg in (day.morning, day.afternoon):
        if seg.places:
          _clear_segment(seg, why_start)
      if day.evening.places:
        _clear_segment(day.evening, "A relaxed dinner near your hotel is the plan for tonight.")
      changed = True
  if e_min is not None and e_min < 18 * 60 and not getattr(day.food_stop_dinner, "skipped", False):
    day.food_stop_dinner.skipped = True
    changed = True
  return changed


def last_stop_end_minutes(day: Any) -> Optional[int]:
  """When the day's last planned activity ends (minutes), from the time windows; None if unknown."""
  for seg in (day.evening, day.afternoon, day.morning):
    if seg and seg.places:
      times = parse_clock(seg.time_window)
      if len(times) >= 2:
        return times[1] if times[1] > times[0] else 24 * 60 - 1
  return None


def return_to_hotel_card(day: Any, hotel: Dict[str, Any], leg: Dict[str, Any], last_name: str) -> Dict[str, Any]:
  """End-of-day step: 'after {last stop}, go back to {hotel}' with a map link and an approximate time."""
  mins = leg.get("minutes") if leg else None
  end = last_stop_end_minutes(day)
  leave = None
  if end is not None:
    # the plan's evening window often runs to bedtime; head back no later than 22:00 and not before the last stop ends
    leave = min(end, _hhmm_to_min(EVENING_END) or end)
  text = f"After {last_name}, head back to {hotel.get('name') or 'your hotel'} to rest."
  out: Dict[str, Any] = {
      "type": "return_to_hotel",
      "hotel_name": hotel.get("name"),
      "hotel_address": hotel.get("address"),
      "from_name": last_name,
      "text": text,
      "leave_at": _fmt_min(leave) if leave is not None else None,
      "arrive_at": _fmt_min(leave + int(mins)) if (leave is not None and mins) else None,
      "directions": leg,
  }
  return out
