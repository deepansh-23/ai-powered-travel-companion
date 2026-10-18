"""Train recommendations built only from real data returned by the providers.

1. A transparent, rule-based ranking decides WHICH trains to recommend (fastest, most
   comfortable, cheapest when real fares exist, best overall). It never invents a fare,
   an availability status or a class.
2. When Gemini is configured it only writes the short comparison text around those facts.
   Its answer is rejected (and the rule-based text is used) if it mentions money that is
   not in the data, so the AI can never present made-up prices.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models.transport import TrainAdvice, TrainAdvicePick, TransportOption

logger = logging.getLogger(__name__)

CLASS_RANK = {"SL": 1, "3A": 2, "2A": 3, "1A": 4}
_PREMIUM = ("vande", "rajdhani", "shatabdi", "tejas", "duronto", "gatimaan", "humsafar", "raj", "sht", "drnt")
_AVAIL_SCORE = {"AVAILABLE": 0.0, "RAC": 0.5, "WL": 1.0}

_AI_SYSTEM_PROMPT = (
    "You help travellers choose between Indian trains. You are given verified facts as JSON. "
    "Use ONLY those facts. Never invent fares, seat availability, timings or classes. "
    "If fares or availability are missing in the data, say plainly that they could not be compared. "
    "Write 3 to 4 short sentences in plain text (no markdown, no bullet points) that compare journey time, "
    "comfort and the user's preference, and end with one clear recommendation."
)


# ---------------------------------------------------------------- facts (plain dicts: easy to test)
def build_facts(option: TransportOption) -> Dict[str, Any]:
    raw = option.raw_provider_data or {}
    classes: Dict[str, Dict[str, Any]] = {}
    fa = option.fare_availability
    if fa:
        for c in fa.classes:
            classes[c.code] = {
                "offered": c.offered,
                "fare": c.fare_per_person,
                "availability": c.availability_status,
            }
    return {
        "id": option.id,
        "number": option.number or "",
        "name": (option.operator or "").replace("Indian Railways (", "").rstrip(")") or "Train",
        "type": str(raw.get("train_type") or ""),
        "duration_minutes": option.duration_minutes,
        "duration_text": option.duration_formatted or f"{option.duration_minutes}m",
        "stops": option.stops,
        "departure": option.departure_time,
        "arrival": option.arrival_time,
        "classes": classes,
    }


def _offered_selected(f: Dict[str, Any]) -> List[str]:
    return [code for code, c in f["classes"].items() if c.get("offered") is True]


def comfort_tier(f: Dict[str, Any]) -> int:
    text = f"{f['name']} {f['type']}".lower()
    if any(w in text for w in _PREMIUM):
        return 3
    if "superfast" in text or re.search(r"\bsf\b", text) or "express" in text:
        return 2
    return 1


def best_class_rank(f: Dict[str, Any]) -> int:
    return max((CLASS_RANK.get(c, 0) for c in _offered_selected(f)), default=0)


def _fares(f: Dict[str, Any]) -> List[float]:
    return [c["fare"] for c in f["classes"].values() if c.get("offered") is True and c.get("fare")]


def _availabilities(f: Dict[str, Any]) -> List[str]:
    return [c["availability"] for c in f["classes"].values() if c.get("offered") is True and c.get("availability")]


def usable_trains(facts: List[Dict[str, Any]], selected_classes: List[str]) -> List[Dict[str, Any]]:
    """Trains that carry at least one chosen class. If classes could not be verified, nothing is filtered out."""
    if not selected_classes:
        return facts
    verified_any = any(c.get("offered") is not None for f in facts for c in f["classes"].values())
    if not verified_any:
        return facts
    return [f for f in facts if _offered_selected(f)]


def _norm(value: float, lo: float, hi: float) -> float:
    return 0.0 if hi <= lo else (value - lo) / (hi - lo)


def overall_scores(facts: List[Dict[str, Any]], preference: str) -> Dict[str, float]:
    """Lower is better. Only the signals that really exist take part (weights are renormalised)."""
    if not facts:
        return {}
    durs = [f["duration_minutes"] for f in facts if f["duration_minutes"] > 0] or [1]
    lo_d, hi_d = min(durs), max(durs)
    all_fares = [min(_fares(f)) for f in facts if _fares(f)]
    pref = (preference or "best-overall").lower()
    weights = {"duration": 0.40, "comfort": 0.30, "availability": 0.15, "fare": 0.15}
    if pref == "fastest":
        weights.update(duration=0.60, comfort=0.15, availability=0.15, fare=0.10)
    elif pref == "cheapest":
        weights.update(duration=0.20, comfort=0.10, availability=0.15, fare=0.55)
    scores: Dict[str, float] = {}
    for f in facts:
        parts: List[Tuple[float, float]] = []
        parts.append((weights["duration"], _norm(f["duration_minutes"], lo_d, hi_d)))
        comfort = (comfort_tier(f) * 2 + best_class_rank(f)) / (3 * 2 + 4)
        parts.append((weights["comfort"], 1.0 - comfort))
        av = _availabilities(f)
        if av:
            parts.append((weights["availability"], min(_AVAIL_SCORE[a] for a in av)))
        if _fares(f) and len(all_fares) >= 2:
            parts.append((weights["fare"], _norm(min(_fares(f)), min(all_fares), max(all_fares))))
        total_w = sum(w for w, _ in parts)
        scores[f["id"]] = sum(w * v for w, v in parts) / total_w if total_w else 1.0
    return scores


def _title(f: Dict[str, Any]) -> str:
    return f"{f['name']} ({f['number']})".strip() if f["number"] else f["name"]


def _reasons(f: Dict[str, Any], pool: List[Dict[str, Any]]) -> List[str]:
    out = []
    shortest = min(p["duration_minutes"] for p in pool)
    if f["duration_minutes"] == shortest and len(pool) > 1:
        out.append(f"Shortest journey of the options found ({f['duration_text']})")
    else:
        out.append(f"Journey time {f['duration_text']}")
    tier = comfort_tier(f)
    if tier == 3:
        out.append("Premium-category train (usually faster with better service)")
    offered = _offered_selected(f)
    if offered:
        out.append("Has your chosen class(es): " + ", ".join(offered))
    fares = _fares(f)
    if fares:
        out.append(f"Fare from ₹{int(min(fares)):,} per person (provider data)")
    av = _availabilities(f)
    if av:
        out.append("Seat availability: " + ", ".join(sorted(set(av))))
    return out


def pick_trains(facts: List[Dict[str, Any]], selected_classes: List[str], preference: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Returns (picks, caveats). picks: [{'labels': [...], 'facts': f}] with one entry per distinct train."""
    pool = usable_trains(facts, selected_classes)
    caveats: List[str] = []
    if not pool:
        return [], ["None of the trains found carries the class(es) you selected. Try other classes or another date."]
    if selected_classes and not any(c.get("offered") is not None for f in facts for c in f["classes"].values()):
        caveats.append("Train classes could not be verified, so every train is shown.")
    if not any(_fares(f) for f in pool):
        caveats.append("Fares are not available from the data source, so cost could not be compared.")
    if not any(_availabilities(f) for f in pool):
        caveats.append("Seat availability (Available / RAC / Waiting list) is not available from the data source.")

    labels: Dict[str, List[str]] = {}

    def add(f: Dict[str, Any], label: str) -> None:
        labels.setdefault(f["id"], [])
        if label not in labels[f["id"]]:
            labels[f["id"]].append(label)

    scores = overall_scores(pool, preference)
    best = min(pool, key=lambda f: (scores[f["id"]], f["duration_minutes"]))
    add(best, "Best overall")
    add(min(pool, key=lambda f: (f["duration_minutes"] or 10**9, f["stops"])), "Fastest")
    add(max(pool, key=lambda f: (comfort_tier(f), best_class_rank(f), -f["duration_minutes"])), "Most comfortable")
    with_fares = [f for f in pool if _fares(f)]
    if len(with_fares) >= 2:
        add(min(with_fares, key=lambda f: min(_fares(f))), "Cheapest")

    if len(labels) < 2 and len(pool) >= 2:  # one train won everything: still show a sensible alternative
        others = [f for f in pool if f["id"] != best["id"]]
        add(min(others, key=lambda f: (scores[f["id"]], f["duration_minutes"])), "Good alternative")

    order = ["Best overall", "Fastest", "Most comfortable", "Cheapest", "Good alternative"]
    ranked = sorted(labels.items(), key=lambda kv: min(order.index(l) for l in kv[1]))
    by_id = {f["id"]: f for f in pool}
    return [{"labels": ls, "facts": by_id[i]} for i, ls in ranked], caveats


def rule_based_summary(picks: List[Dict[str, Any]], caveats: List[str], preference: str) -> str:
    if not picks:
        return caveats[0] if caveats else "No trains to compare."
    top = picks[0]["facts"]
    text = (f"{_title(top)} is the best overall option from the data available "
            f"({top['duration_text']}, {'direct' if top['stops'] == 0 else str(top['stops']) + ' halts'}).")
    for p in picks[1:]:
        f = p["facts"]
        text += f" {' / '.join(p['labels'])}: {_title(f)} ({f['duration_text']})."
    if caveats:
        text += " Note: " + " ".join(caveats)
    return text


def ai_text_is_safe(text: str, facts: List[Dict[str, Any]]) -> bool:
    """Reject AI text that talks about money when no real fare exists, or is oddly long/empty."""
    if not text or len(text) > 1200:
        return False
    has_fares = any(_fares(f) for f in facts)
    if not has_fares and re.search(r"(₹|\brs\.?\s*\d|\binr\s*\d|\d\s*rupees|\bfare of\b.*\d)", text, re.I):
        return False
    return True


class TrainAdvisorService:
    async def advise(self, trains: List[TransportOption], selected_classes: List[str], preference: str) -> Optional[TrainAdvice]:
        if not trains:
            return None
        facts = [build_facts(t) for t in trains]
        picks, caveats = pick_trains(facts, selected_classes, preference)
        if not picks:
            return TrainAdvice(headline="No suitable train found", picks=[], summary=rule_based_summary(picks, caveats, preference),
                               source="rule-based", caveats=caveats)

        pool = usable_trains(facts, selected_classes)
        pick_models = [
            TrainAdvicePick(label=" · ".join(p["labels"]), option_id=p["facts"]["id"], title=_title(p["facts"]),
                            reasons=_reasons(p["facts"], pool))
            for p in picks
        ]
        summary, source = rule_based_summary(picks, caveats, preference), "rule-based"

        ai_ready = (not settings.MOCK_MODE) and bool(settings.GEMINI_API_KEY) and len(pool) >= 2
        if ai_ready:
            try:
                from app.services.ai_service import ai_service
                shortlist = [p["facts"] for p in picks] + [f for f in pool if f["id"] not in {p["facts"]["id"] for p in picks}][:3]
                prompt = (
                    f"Traveller preference: {preference}. Chosen classes: {', '.join(selected_classes) or 'none chosen'}.\n"
                    f"Rule-based shortlist (best first): {json.dumps([{'labels': p['labels'], 'train': _title(p['facts'])} for p in picks])}\n"
                    f"Verified train facts: {json.dumps(shortlist, ensure_ascii=False)}\n"
                    f"Data gaps: {json.dumps(caveats)}"
                )
                text = await asyncio.wait_for(
                    asyncio.to_thread(ai_service._generate_with_fallback, prompt, _AI_SYSTEM_PROMPT), timeout=25
                )
                text = (text or "").strip()
                if ai_text_is_safe(text, pool):
                    summary, source = text, "ai"
                else:
                    logger.info("AI train summary rejected by safety check; using rule-based text.")
            except Exception as exc:
                logger.info(f"AI train advice unavailable, using rule-based text: {exc}")

        top = picks[0]["facts"]
        return TrainAdvice(headline=f"Recommended: {_title(top)}", picks=pick_models, summary=summary, source=source, caveats=caveats)


train_advisor_service = TrainAdvisorService()
