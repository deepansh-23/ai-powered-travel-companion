"""Pure trip-planning helpers for multi-area trips (no framework imports, easy to test).

  * recommended_areas / scope_advice   how many areas make sense for a trip length
  * allocate_days                      which area each day is spent in
  * plan_stay_blocks                   which days share one hotel ("stay blocks")
  * block_transfers                    rough travel between consecutive stays (clearly an estimate)
"""

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

MAX_AREAS = 6
# Changing hotel is tiring, so the same hotel is kept for the whole stay in one place. A new hotel is only
# suggested when the traveller moves to another place, or when a group of days is so far from the hotel that
# a lot of time would be lost travelling back and forth (see plan_stay_blocks).
MAX_NIGHTS_PER_HOTEL = 14
SPLIT_DISTANCE_KM = 20.0       # sights further than this from the hotel area may justify a different hotel
MIN_DAYS_NEW_AREA = 2          # ...but only if at least this many days are spent around the new spot
MIN_DAYS_BEFORE_SPLIT = 2      # ...and the first hotel has been used for at least this many days
ROAD_FACTOR = 1.3              # straight line -> typical road distance
ROAD_SPEED_KMH = 50.0
COST_PER_KM_PER_PERSON = 3.5   # INR, mixed bus/train/shared cab: an ESTIMATE, always labelled as one


LONG_TRANSFER_KM = 200  # from this distance on, the traveller chooses how to travel between two stays


def transfer_needs_choice(kind: Optional[str], distance_km: float) -> bool:
  """Country trips always ask how to get between places; other trips ask once the move is long."""
  return kind == "country" or distance_km >= LONG_TRANSFER_KM


# ---------------------------------------------------------------- scope advice
def recommended_areas(kind: str, days: int) -> int:
    """A sensible number of places to stay in, so the trip is not all travelling."""
    days = max(1, int(days or 1))
    if kind == "country":
        return max(1, min(5, days // 3))
    if kind == "state":
        return max(1, min(5, days // 2))
    return max(1, min(3, days // 3))  # city / area: the city plus a few nearby towns


def scope_advice(kind: str, name: str, days: int, n_selected: int = 0) -> str:
    rec = recommended_areas(kind, days)
    big = {"country": "a whole country", "state": "a whole state"}.get(kind)
    if kind in ("country", "state"):
        text = (f"{name} is {big}. With {days} day(s), about {rec} place(s) to stay in works best, "
                "so less time is spent travelling between them.")
    else:
        text = (f"With {days} day(s) in {name}, you can stay in the city only"
                f"{' or add up to ' + str(rec - 1) + ' nearby place(s)' if rec > 1 else ''}.")
    if n_selected > rec:
        text += f" You picked {n_selected}; that is possible but will mean more travelling."
    return text


# ---------------------------------------------------------------- allocation
def allocate_days(areas: List[str], days: int, weights: Optional[List[float]] = None) -> List[str]:
    """Returns one area name per day (length == days). Every used area gets at least one day;
    the remaining days go to areas with more to see (larger weight) using largest remainders."""
    days = max(1, int(days))
    unique: List[str] = []
    for a in areas or []:
        a = (a or "").strip()
        if a and a.lower() not in {u.lower() for u in unique}:
            unique.append(a)
    unique = unique[: min(len(unique), days, MAX_AREAS)]
    n = len(unique)
    if n == 0:
        return []
    w = list(weights[:n]) if weights and len(weights) >= n and all(x and x > 0 for x in weights[:n]) else [1.0] * n
    counts = [1] * n
    extra = days - n
    if extra > 0:
        total = float(sum(w))
        quotas = [extra * x / total for x in w]
        whole = [int(q) for q in quotas]
        leftover = extra - sum(whole)
        for i in sorted(range(n), key=lambda i: quotas[i] - whole[i], reverse=True)[:leftover]:
            whole[i] += 1
        counts = [c + x for c, x in zip(counts, whole)]
    schedule: List[str] = []
    for area, c in zip(unique, counts):
        schedule += [area] * c
    return schedule


# ---------------------------------------------------------------- geometry
def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _centroid(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    if not points:
        return None
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


# ---------------------------------------------------------------- stay blocks
def plan_stay_blocks(
    days: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    max_nights: int = MAX_NIGHTS_PER_HOTEL,
    split_km: float = SPLIT_DISTANCE_KM,
) -> List[Dict[str, Any]]:
    """Groups consecutive days into hotel stays.

    days: [{'day_number': 1, 'area': 'Jaipur', 'points': [(lat, lon), ...], 'places': ['Amber Fort', ...]}]

    A new stay starts ONLY when
      * the area (city) changes, or
      * a run of at least MIN_DAYS_NEW_AREA days is spent more than `split_km` away from the hotel area
        (so the traveller can see one cluster of places from one hotel and the next cluster from another), or
      * the stay would exceed `max_nights` (a safety cap).
    A single far-away day does NOT trigger a hotel change: it is a day trip. Two hotels in the same
    neighbourhood are never suggested. The last day is the departure day, so the final stay has one
    night fewer than its days.
    """
    def _pts(d: Dict[str, Any]) -> List[Tuple[float, float]]:
        return [tuple(p) for p in (d.get("points") or []) if p and p[0] is not None and p[1] is not None]

    def _far_cluster_days(i: int, area: str, ref: Tuple[float, float]) -> int:
        """How many consecutive days from day index i stay around the same far-away spot (same area)."""
        c0 = _centroid(_pts(days[i]))
        n = 0
        for d in days[i:]:
            if (d.get("area") or "").strip().lower() != area.lower():
                break
            c = _centroid(_pts(d))
            if not c or not c0 or haversine_km(c0, c) > split_km or haversine_km(ref, c) <= split_km:
                break
            n += 1
        return n

    runs: List[Dict[str, Any]] = []
    for i, d in enumerate(days):
        pts = _pts(d)
        area = (d.get("area") or "").strip()
        cur = runs[-1] if runs else None
        start_new = cur is None or area.lower() != cur["area"].lower() or len(cur["days"]) >= max_nights
        if not start_new and pts and len(cur["days"]) >= MIN_DAYS_BEFORE_SPLIT:
            ref = cur["first_point"]      # where the traveller started the stay (a day trip must not shift it)
            c = _centroid(pts)
            if ref and c and haversine_km(ref, c) > split_km and _far_cluster_days(i, area, ref) >= MIN_DAYS_NEW_AREA:
                start_new = True
        if start_new:
            runs.append({"area": area, "days": [], "points": [], "places": [], "first_point": _centroid(pts)})
            cur = runs[-1]
        cur["days"].append(int(d.get("day_number", len(cur["days"]) + 1)))
        cur["points"] += pts
        cur["places"] += [p for p in (d.get("places") or []) if p]

    try:
        base = date.fromisoformat(start_date) if start_date else None
    except ValueError:
        base = None

    blocks: List[Dict[str, Any]] = []
    for i, r in enumerate(runs):
        n_days = len(r["days"])
        nights = n_days - 1 if i == len(runs) - 1 else n_days
        first_day = r["days"][0]
        c = _centroid(r["points"])
        check_in = (base + timedelta(days=first_day - 1)) if base else None
        anchor = r["places"][0] if r["places"] else r["area"]
        blocks.append({
            "index": i,
            "area": r["area"],
            "start_day": first_day,
            "end_day": r["days"][-1],
            "days": n_days,
            "nights": max(0, nights),
            "needs_hotel": nights > 0,
            "check_in": check_in.isoformat() if check_in else None,
            "check_out": (check_in + timedelta(days=max(0, nights))).isoformat() if check_in else None,
            "places": r["places"][:6],
            "centroid": {"lat": round(c[0], 5), "lon": round(c[1], 5)} if c else None,
            "search_query": anchor if anchor.lower() == r["area"].lower() or not r["area"] else f"{anchor}, {r['area']}",
        })
    return blocks


def block_transfers(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rough travel between consecutive stays. Distances are straight-line x 1.3, so every number is an estimate."""
    out: List[Dict[str, Any]] = []
    for a, b in zip(blocks, blocks[1:]):
        if not a.get("centroid") or not b.get("centroid"):
            continue
        km = haversine_km((a["centroid"]["lat"], a["centroid"]["lon"]), (b["centroid"]["lat"], b["centroid"]["lon"])) * ROAD_FACTOR
        if km < 3:
            continue
        out.append({
            "from_area": a["area"], "to_area": b["area"], "from_stay": a["index"], "to_stay": b["index"],
            "distance_km": int(round(km)),
            "air_km": int(round(km / ROAD_FACTOR)),   # straight line: the distance a flight covers
            "hours": round(km / ROAD_SPEED_KMH, 1),
            "cost_per_person": int(round(km * COST_PER_KM_PER_PERSON)),
            "note": ("Long transfer: check trains or a short flight." if km > 400
                     else "Road/rail estimate; check timetables."),
        })
    return out
