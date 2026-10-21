"""Trip budget maths (pure Python, no framework imports, easy to test).

Everything the traveller sees in the "total price breakdown" comes from here, and every
line is tagged so the UI can tell real provider quotes from estimates:

  live      real quote from a provider (flight, hotel)
  estimate  derived from the daily budget the traveller chose

Transport prices are PER PERSON and are multiplied by the number of travellers here.
Hotel prices are per room for the whole stay and are multiplied by the number of rooms.
"""

import math
from typing import Any, Dict, List, Optional

# How the traveller's daily spending budget is split into everyday categories (shares add up to 1.0)
DAILY_SPLIT = (
    ("food", "Food & drinks", 0.40),
    ("local_transport", "Local transport (taxis, metro, autos)", 0.20),
    ("activities", "Sightseeing, tickets & activities", 0.30),
    ("misc", "Shopping, tips & small extras", 0.10),
)
CONTINGENCY_PCT = 10  # applied to the estimated items only, never to live quotes


def default_rooms(travelers: int) -> int:
    """One room for every two travellers."""
    return max(1, math.ceil(max(1, travelers) / 2))


def _money(v: Optional[float]) -> int:
    return int(round(v or 0))


def build_budget(
    *,
    travelers: int,
    days: int,
    per_day_per_person: float,
    outbound_pp: Optional[float] = None,
    return_pp: Optional[float] = None,
    hotel_total_per_room: Optional[float] = None,
    hotel_nightly: Optional[float] = None,
    rooms: Optional[int] = None,
    hotels: Optional[List[Dict[str, Any]]] = None,
    transfers: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    travelers = max(1, int(travelers or 1))
    days = max(1, int(days or 1))
    nights = max(1, days - 1)
    rooms = int(rooms) if rooms else default_rooms(travelers)

    missing: List[str] = []
    lines: List[Dict[str, Any]] = []

    # --- live quotes -------------------------------------------------------
    def transport_line(key: str, label: str, price_pp: Optional[float]) -> None:
        if price_pp:
            lines.append({"key": key, "label": label, "kind": "live", "per_person": _money(price_pp),
                          "total": _money(price_pp * travelers),
                          "note": f"{_money(price_pp):,} per person x {travelers}"})
        else:
            missing.append(f"{label}: no price selected, so it is not included in the total.")

    transport_line("outbound", "Outbound travel", outbound_pp)
    transport_line("return", "Return travel", return_pp)

    if hotels is not None:
        # several stays: [{'label', 'nights', 'total_per_room', 'nightly'}] ('skipped' stays are left out on purpose)
        for h in hotels:
            per_room = h.get("total_per_room") or ((h.get("nightly") or 0) * (h.get("nights") or 0)) or None
            if per_room:
                total = per_room * rooms
                lines.append({"key": f"stay_{h.get('index', len(lines))}", "label": f"Hotel: {h.get('label', 'Stay')}",
                              "kind": "live", "per_person": _money(total / travelers), "total": _money(total),
                              "note": f"{_money(per_room):,} per room x {rooms} room(s) for {h.get('nights', 0)} night(s)"})
            elif not h.get("skipped"):
                missing.append(f"Hotel in {h.get('label', 'this stay')}: no hotel selected, so it is not included.")
        stay_per_room = None
    else:
        stay_per_room = hotel_total_per_room if hotel_total_per_room else (hotel_nightly * nights if hotel_nightly else None)
    if hotels is not None:
        pass
    elif stay_per_room:
        stay_total = stay_per_room * rooms
        lines.append({"key": "stay", "label": "Hotel stay", "kind": "live",
                      "per_person": _money(stay_total / travelers), "total": _money(stay_total),
                      "note": f"{_money(stay_per_room):,} per room x {rooms} room(s) for {nights} night(s)"})
    else:
        missing.append("Hotel stay: no hotel selected, so it is not included in the total.")

    # --- travel between stays (estimate) ---------------------------------------
    if transfers:
        est_pp = est_km = 0
        for i, t in enumerate(transfers):
            mode = t.get("mode")
            label = t.get("label") or f"{t.get('from_area', '')} → {t.get('to_area', '')}".strip()
            if t.get("live_price_pp"):
                # a flight the traveller picked: a real quote, per person
                pp = t["live_price_pp"]
                lines.append({"key": f"transfer_{i}", "label": f"Travel {label} ({mode})", "kind": "live",
                              "per_person": _money(pp), "total": _money(pp * travelers),
                              "note": f"{_money(pp):,} per person x {travelers}"})
            elif mode in ("train", "other"):
                missing.append(f"Travel {label} by {mode}: no fare is available from the data source, so it is not in the total.")
            else:  # a cab, or no choice made: the distance-based estimate
                est_pp += t.get("cost_per_person", 0)
                est_km += t.get("distance_km", 0)
        if est_pp or est_km:
            lines.append({"key": "transfers", "label": "Travel between stays by cab (estimate)", "kind": "estimate",
                          "per_person": _money(est_pp), "total": _money(est_pp * travelers),
                          "note": f"about {est_km:,} km in total at a rough per-km rate; check real fares"})

    # --- estimates from the daily budget --------------------------------------
    estimate_total = 0
    for key, label, share in DAILY_SPLIT:
        pp = per_day_per_person * share * days
        total = pp * travelers
        estimate_total += _money(total)
        lines.append({"key": key, "label": label, "kind": "estimate", "per_person": _money(pp),
                      "total": _money(total),
                      "note": f"{_money(per_day_per_person * share):,} per person per day x {days} day(s)"})

    contingency = _money(estimate_total * CONTINGENCY_PCT / 100.0)
    lines.append({"key": "contingency", "label": f"Contingency ({CONTINGENCY_PCT}% of estimated items)",
                  "kind": "estimate", "per_person": _money(contingency / travelers), "total": contingency,
                  "note": "A small cushion for price changes and surprises"})

    live_total = sum(l["total"] for l in lines if l["kind"] == "live")
    est_total = sum(l["total"] for l in lines if l["kind"] == "estimate")
    grand = live_total + est_total

    per_day = [{"label": label, "per_person_per_day": _money(per_day_per_person * share)}
               for _, label, share in DAILY_SPLIT]

    return {
        "travelers": travelers,
        "days": days,
        "nights": nights,
        "rooms": rooms,
        "lines": lines,
        "daily": {"per_person_per_day": _money(per_day_per_person), "split": per_day,
                  "group_per_day": _money(per_day_per_person * travelers)},
        "live_total": live_total,
        "estimate_total": est_total,
        "grand_total": grand,
        "per_person_total": _money(grand / travelers),
        "missing": missing,
        "currency": "INR",
    }
