"""Batch B: arrival / departure / hotel-change notes, walk and drive times, friendlier prompt."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.directions_service import _Point, build_leg
from app.utils.day_timing import (
    arrival_card, cab_estimate, day_windows, departure_card, hotel_change_card, parse_dt, window_prompt_lines,
)

client = TestClient(app)

OUT = {"mode": "flight", "operator": "IndiGo", "number": "6E 123", "origin": "DEL (Indira Gandhi Airport)",
       "destination": "GOI (Dabolim Airport)", "departure_time": "2099-03-10 08:00",
       "arrival_time": "2099-03-10 10:15", "duration_formatted": "2h 15m", "price": 4000}
BACK = {"mode": "flight", "operator": "Air India", "number": "AI 9", "origin": "GOI (Dabolim Airport)",
        "destination": "DEL (Indira Gandhi Airport)", "departure_time": "2099-03-13 18:30",
        "arrival_time": "2099-03-13 20:45", "duration_formatted": "2h 15m", "price": 3500}


# ------------------------------------------------------------------ timing rules
def test_day_one_starts_after_landing_exit_cab_and_settling_in():
    w = day_windows(OUT, BACK, 4)
    assert w["start"] == "13:00"      # 10:15 + 45 exit + 40 cab = 11:40 at the hotel, + 60 min rest (before check-in), rounded up to :30
    assert w["end"] == "15:20"        # 18:30 - 2h airport buffer - 40 cab - 30 check-out
    assert day_windows(None, None, 3) == {"start": None, "end": None}
    assert day_windows({"mode": "train", "arrival_time": "garbage"}, None, 3)["start"] is None


def test_late_arrival_only_gets_a_relaxed_evening_and_prompt_forbids_journey_talk():
    late = day_windows({"mode": "flight", "arrival_time": "2099-03-10 18:10"}, None, 3)
    assert "relaxed dinner" in window_prompt_lines(late, 3)[0]            # 18:10 landing -> only dinner is realistic
    afternoon = window_prompt_lines(day_windows({"mode": "flight", "arrival_time": "2099-03-10 14:10"}, None, 3), 3)[0]
    assert "relaxed dinner" not in afternoon and "START at 17:30" in afternoon and "dinner stop" in afternoon  # still a real plan
    text = " ".join(window_prompt_lines(day_windows(OUT, BACK, 4), 4))
    assert "START at 13:00" in text and "FINISHED by 15:20" in text and "Do NOT write about the flight" in text


def test_arrival_day_plan_is_trimmed_to_the_free_hours_and_meals_skipped():
    from app.models.itinerary import FoodStop, ItineraryDay, ItinerarySegment, ItineraryPlaceItem
    from app.utils.day_timing import fit_day_to_window, parse_clock, ready_time_after_arrival
    assert parse_clock("08:30 AM – 12:00 PM") == [510, 720] and parse_clock("5:30 PM – 10:00 PM") == [1050, 1320]
    place = lambda n: ItineraryPlaceItem(name=n, category="x")
    seg = lambda tw, *names: ItinerarySegment(time_window=tw, title="T", description="d", places=[place(n) for n in names])
    food = lambda: FoodStop(name="F", cuisine="c", recommendation="r")
    day = ItineraryDay(day_number=1, theme="t", estimated_day_cost="0", morning=seg("08:30 AM – 12:00 PM", "A"),
                       food_stop_lunch=food(), afternoon=seg("12:30 PM – 04:30 PM", "B"), food_stop_dinner=food(),
                       evening=seg("05:30 PM – 10:30 PM", "C"))
    start = ready_time_after_arrival({"mode": "flight", "arrival_time": "2099-03-10 14:10"})
    assert start == "17:30"
    assert fit_day_to_window(day, start)
    assert day.morning.places == [] and day.afternoon.places == []      # these hours are spent travelling and resting
    assert [p.name for p in day.evening.places] == ["C"] and day.evening.time_window == "17:30 – 22:00"
    assert day.food_stop_lunch.skipped and not day.food_stop_dinner.skipped


def test_cab_time_comes_from_distance_or_a_labelled_default():
    known = cab_estimate((15.38, 73.83), (15.50, 73.83))
    assert known["known"] and known["km"] > 10 and known["minutes"] >= 10
    assert cab_estimate(None, (1, 1)) == {"minutes": 40, "km": None, "known": False}


def test_arrival_card_is_short_and_has_the_agreed_steps():
    card = arrival_card(OUT, {"name": "Hotel Sea"}, cab_estimate((15.38, 73.83), (15.50, 73.83)), "Delhi", "Goa")
    text = " ".join(card["lines"])
    assert card["type"] == "arrival" and "Today you fly Delhi → Goa with IndiGo 6E 123" in text
    assert "leaves 08:00, arrives 10:15" in text and "2h 15m" in text
    assert "45 minutes" in text and "Cab to Hotel Sea" in text and "(estimate" in text
    assert "Check-in is usually from 14:00" in text and "Early check-in is not guaranteed" in text
    assert "lunch" not in text.lower() and "in-flight" not in text.lower()


def test_departure_card_uses_the_two_hour_airport_rule():
    card = departure_card(BACK, {"name": "Hotel Sea"}, cab_estimate(None, None), "Delhi", "Goa")
    text = " ".join(card["lines"])
    assert "Check out by 11:00" in text and "Be at the airport by 16:30 (2 hours before departure)" in text
    train = departure_card({**BACK, "mode": "train"}, None, cab_estimate(None, None))
    assert "1 hour before departure" in " ".join(train["lines"])


def test_hotel_change_card_names_both_hotels_and_the_distance():
    cab = cab_estimate((15.38, 73.83), (15.50, 73.83))
    card = hotel_change_card({"name": "Hotel A"}, {"name": "Hotel B"}, cab)
    text = " ".join(card["lines"])
    assert card["type"] == "hotel_change" and "Hotel A" in text and "Hotel B" in text and "11:00" in text and "14:00" in text
    assert card["distance_km"] == cab["km"] and parse_dt("2099-03-10 08:00") is not None


# ------------------------------------------------------------------ walk and drive time on every stop
def test_each_leg_shows_both_walking_and_driving_time():
    leg = build_leg(_Point("A", None, 31.620, 74.876), _Point("B", None, 31.6215, 74.8795), "public")
    assert leg["walk_minutes"] and leg["drive_minutes"] and leg["walk_minutes"] > leg["drive_minutes"] - 1
    assert "on foot" in leg["summary"] and "by car or auto" in leg["summary"] and "head" in leg["summary"]
    no_coords = build_leg(_Point("A"), _Point("B"), "public")
    assert no_coords["walk_minutes"] is None and "open the map" in no_coords["summary"]


# ------------------------------------------------------------------ finalize adds the cards
BASE = {"destination": "Goa", "source": "Delhi", "departure_date": "2099-03-10", "return_date": "2099-03-13",
        "duration_days": 4, "budget_per_person_per_day": 3000, "travelers_count": 2, "areas": ["Goa", "Gokarna"]}


def _finalize(plan, stays, out=OUT, back=BACK):
    plan["selected_outbound_transport"] = out
    plan["selected_return_transport"] = back
    return client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": stays, "travelers_count": 2})


def test_finalize_adds_arrival_hotel_change_and_departure_cards():
    plan = client.post("/api/itinerary/generate", json=BASE).json()
    blocks = [b for b in plan["stay_blocks"] if b["needs_hotel"]]
    assert len(blocks) == 2
    stays = [{"block_index": blocks[0]["index"], "hotel": {"name": "Hotel Goa", "latitude": 15.50, "longitude": 73.83}},
             {"block_index": blocks[1]["index"], "hotel": {"name": "Hotel Gokarna", "latitude": 14.55, "longitude": 74.32}}]
    r = _finalize(plan, stays)
    assert r.status_code == 200, r.text
    days = {d["day_number"]: d for d in r.json()["days"]}
    first, last = days[1], days[4]
    assert [n["type"] for n in first["notes"]] == ["arrival"]
    assert "Today you fly" in " ".join(first["notes"][0]["lines"])
    assert [n["type"] for n in last["notes"]] == ["departure"]
    change_day = days[blocks[1]["start_day"]]
    change = [n for n in change_day["notes"] if n["type"] == "hotel_change"]
    assert change and change[0]["from_hotel"] == "Hotel Goa" and change[0]["to_hotel"] == "Hotel Gokarna"
    assert change[0]["distance_km"] and change[0]["distance_km"] > 50


def test_finalize_without_transport_or_hotels_adds_no_cards_and_does_not_fail():
    plan = client.post("/api/itinerary/generate", json={**BASE, "areas": []}).json()
    r = client.post("/api/itinerary/finalize", json={"itinerary": plan, "stay_hotels": [], "travelers_count": 2})
    assert r.status_code == 200 and all(d["notes"] == [] for d in r.json()["days"])


def test_finalizing_twice_does_not_stack_cards():
    plan = client.post("/api/itinerary/generate", json=BASE).json()
    first = _finalize(plan, []).json()
    again = _finalize(first, []).json()
    assert len(again["days"][0]["notes"]) == 1
