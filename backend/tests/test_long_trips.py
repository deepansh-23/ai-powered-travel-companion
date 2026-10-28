"""Long trips: every requested day must be planned (10 days means 10 days), whatever the AI returns.

The AI call is faked from the prompt, so nothing here uses Gemini.
"""

import asyncio
import json
import re

import pytest

from app.models.itinerary import ItineraryRequest
from app.services.ai_service import ai_service


def _day(n, area=None):
    seg = lambda tw, t: {"time_window": tw, "title": t, "description": "d", "places": [{"name": f"Place {n}-{t}", "category": "x"}]}
    d = {"day_number": n, "theme": f"Theme {n}", "estimated_day_cost": "₹1",
         "morning": seg("09:00 AM – 12:00 PM", "m"), "afternoon": seg("01:00 PM – 04:00 PM", "a"), "evening": seg("05:00 PM – 08:00 PM", "e"),
         "food_stop_lunch": {"name": f"Lunch {n}", "cuisine": "c", "recommendation": "r"},
         "food_stop_dinner": {"name": f"Dinner {n}", "cuisine": "c", "recommendation": "r"}}
    if area:
        d["area"] = area
    return d


class FakeAI:
    """Answers each prompt for the days it asks for. Hooks let a test misbehave."""

    def __init__(self, skip=(), truncate_first=False, fail_days=(), renumber=False):
        self.prompts, self.skip, self.fail_days, self.renumber = [], set(skip), set(fail_days), renumber
        self.truncate_first, self._truncated = truncate_first, False

    @staticmethod
    def wanted(prompt):
        m = re.search(r"Write ONLY days (\d+) to (\d+)", prompt)
        if m:
            return int(m.group(1)), int(m.group(2))
        total = int(re.search(r"detailed (\d+)-day", prompt).group(1))
        return 1, total

    def __call__(self, prompt, system_prompt=None):
        self.prompts.append(prompt)
        first, last = self.wanted(prompt)
        if any(first <= d <= last for d in self.fail_days):
            return "this is not json {{{"
        if self.truncate_first and not self._truncated:
            self._truncated = True
            return '{"title": "x", "days": [{"day_number": 1, "theme": "cut off'
        days = [_day(n) for n in range(first, last + 1) if n not in self.skip]
        if self.renumber:
            for d in days:
                d["day_number"] = 1
        return json.dumps({"title": f"{last - first + 1}-day plan", "trip_overview": "Overview", "days": days})


def _run(req, fake, monkeypatch, places=None):
    monkeypatch.setattr(ai_service, "_generate_with_fallback", fake)
    return asyncio.run(ai_service._generate_live_itinerary(req, verified_places=places or []))


def _req(days, **kw):
    return ItineraryRequest(destination="Rome", duration_days=days, **kw)


# ------------------------------------------------------------------ chunk sizes
def test_chunks_cover_every_day_in_parts_of_at_most_four():
    for total in range(1, 15):
        chunks = ai_service._day_chunks(total)
        covered = [d for a, b in chunks for d in range(a, b + 1)]
        assert covered == list(range(1, total + 1)) and all(b - a + 1 <= 4 for a, b in chunks)
    assert ai_service._day_chunks(4) == [(1, 4)] and ai_service._day_chunks(10) == [(1, 4), (5, 7), (8, 10)]
    assert ai_service._runs_of([1, 2, 3, 4, 5, 9]) == [[1, 2, 3, 4], [5], [9]]


# ------------------------------------------------------------------ the 10-day case from the bug report
def test_ten_day_trip_returns_ten_days_in_order(monkeypatch):
    fake = FakeAI()
    res = _run(_req(10), fake, monkeypatch)
    assert [d.day_number for d in res.days] == list(range(1, 11)) and res.duration_days == 10
    assert len(fake.prompts) == 3                                         # 4 + 3 + 3 days, not one huge answer
    assert res.days[7].theme == "Theme 8" and res.title == "4-day plan" or res.title
    assert all("Free day" != d.theme for d in res.days)


def test_short_trip_is_still_one_request_with_the_original_prompt(monkeypatch):
    fake = FakeAI()
    res = _run(_req(3), fake, monkeypatch)
    assert len(fake.prompts) == 1 and "PART" not in fake.prompts[0] and "Write ONLY days" not in fake.prompts[0]
    assert [d.day_number for d in res.days] == [1, 2, 3]


def test_each_part_gets_only_its_own_days_and_time_rules(monkeypatch):
    fake = FakeAI()
    _run(_req(10, area_schedule=["Rome"] * 5 + ["Florence"] * 5), fake, monkeypatch,
         places=[{"name": "A", "area": "Rome"}, {"name": "B", "area": "Florence"}])
    p1, p2, p3 = fake.prompts
    assert "PART 1 OF 3" in p1 and "days 1 to 4" in p1 and "Day 1: Rome" in p1 and "Day 5" not in p1
    assert "PART 3 OF 3" in p3 and "days 8 to 10" in p3 and "Day 8: Florence" in p3 and "Day 4" not in p3
    assert "- DAY 1" not in p2 and "- DAY 1" not in p3                      # day-1 arrival rule only where day 1 is planned
    assert '"priority": "primary"' in p3 and '"priority": "backup"' in p3


# ------------------------------------------------------------------ AI misbehaviour
def test_days_the_ai_skipped_are_requested_again(monkeypatch):
    fake = FakeAI(skip=[3, 9])
    orig = fake.__call__

    def once_then_ok(prompt, system_prompt=None):
        if "already planned" in prompt:                                  # only the repair request says this
            fake.skip.clear()                                             # the repair request is answered properly
        return orig(prompt, system_prompt)
    res = _run(_req(10), once_then_ok, monkeypatch)
    assert [d.day_number for d in res.days] == list(range(1, 11))
    assert not any(d.theme == "Free day" for d in res.days)
    assert any("Write ONLY days 3 to 3" in p for p in fake.prompts) and any("Write ONLY days 9 to 9" in p for p in fake.prompts)


def test_a_cut_off_answer_is_retried_once(monkeypatch):
    fake = FakeAI(truncate_first=True)
    res = _run(_req(10), fake, monkeypatch)
    assert len(res.days) == 10 and not any(d.theme == "Free day" for d in res.days)
    assert len(fake.prompts) == 4                                         # 3 parts + 1 retry


def test_a_part_that_keeps_failing_becomes_free_days_not_a_short_trip(monkeypatch):
    fake = FakeAI(fail_days=[5, 6, 7])
    res = _run(_req(10), fake, monkeypatch)
    assert [d.day_number for d in res.days] == list(range(1, 11))
    assert [d.theme == "Free day" for d in res.days] == [False] * 4 + [True] * 3 + [False] * 3
    assert res.days[5].morning.places == [] and "Free" in res.days[5].morning.title


def test_when_nothing_can_be_planned_the_original_error_is_raised(monkeypatch):
    with pytest.raises(RuntimeError, match="unexpected response format"):
        _run(_req(10), FakeAI(fail_days=range(1, 11)), monkeypatch)
    with pytest.raises(RuntimeError, match="unexpected response format"):
        _run(_req(3), FakeAI(fail_days=[1, 2, 3]), monkeypatch)


def test_wrong_or_repeated_day_numbers_from_the_ai_do_not_lose_or_shift_days(monkeypatch):
    res = _run(_req(10), FakeAI(renumber=True), monkeypatch)              # the AI labels every day "1"
    assert [d.day_number for d in res.days] == list(range(1, 11))
    assert [d.theme for d in res.days] == [f"Theme {n}" for n in range(1, 11)]


def test_fourteen_days_the_maximum_work_too(monkeypatch):
    res = _run(_req(14), FakeAI(), monkeypatch)
    assert [d.day_number for d in res.days] == list(range(1, 15))
