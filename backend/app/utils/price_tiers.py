"""Pure helpers for the "nearby dates" flight price strip (no framework imports, easy to test).

Colour meaning shown in the UI:  low = green (cheap),  medium = orange,  high = red (expensive).
"""

from datetime import date as _date
from typing import Dict, List, Optional


def classify_price_tiers(prices: Dict[str, Optional[float]]) -> Dict[str, str]:
    """Map each date to 'low' | 'medium' | 'high' | 'unknown' by comparing the dates with each other.

    The price range (cheapest..dearest) is split into three equal bands. A date without a
    price is 'unknown' (never guessed). If every priced date costs the same, or only one
    date has a price, there is nothing to compare, so they are all 'medium'.
    """
    priced = {d: p for d, p in prices.items() if p is not None and p > 0}
    result = {d: "unknown" for d in prices}
    if not priced:
        return result
    lo, hi = min(priced.values()), max(priced.values())
    span = hi - lo
    if span <= 0 or len(priced) == 1:
        for d in priced:
            result[d] = "medium"
        return result
    low_cut, high_cut = lo + span / 3.0, lo + 2.0 * span / 3.0
    for d, p in priced.items():
        result[d] = "low" if p <= low_cut else ("high" if p >= high_cut else "medium")
    return result


def pretty_date(iso: str) -> str:
    """'2026-11-04' -> 'Wed 04 Nov'."""
    return _date.fromisoformat(iso).strftime("%a %d %b")


def build_date_note(entries: List[dict], selected_iso: str, currency_symbol: str = "₹") -> Optional[str]:
    """One plain sentence that tells the traveller whether a nearby date is cheaper.

    entries: [{'date': 'YYYY-MM-DD', 'cheapest_price': float|None}, ...]
    """
    priced = [e for e in entries if e.get("cheapest_price")]
    if not priced:
        return None
    selected = next((e for e in priced if e["date"] == selected_iso), None)
    cheapest = min(priced, key=lambda e: e["cheapest_price"])

    def money(v: float) -> str:
        return f"{currency_symbol}{int(round(v)):,}"

    if selected is None:
        return (f"Cheapest fare among these dates: {pretty_date(cheapest['date'])} "
                f"from {money(cheapest['cheapest_price'])} per person.")
    if cheapest["date"] == selected_iso or cheapest["cheapest_price"] >= selected["cheapest_price"]:
        return (f"Good choice: {pretty_date(selected_iso)} already has the lowest fare "
                f"({money(selected['cheapest_price'])}) among the nearby dates.")
    saving = selected["cheapest_price"] - cheapest["cheapest_price"]
    return (f"Tip: flying on {pretty_date(cheapest['date'])} is about {money(saving)} cheaper per person "
            f"({money(cheapest['cheapest_price'])} instead of {money(selected['cheapest_price'])}). "
            "Fares can change, so check before you book.")
