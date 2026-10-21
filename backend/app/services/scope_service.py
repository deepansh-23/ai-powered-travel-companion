"""Works out how big a destination is (city, state or country) and what to ask the traveller.

A city can be planned as typed. A state or a country is too big for a short trip, so the
planner asks which cities or regions to visit, and where the traveller will land. Suggested
names come from Gemini when it is configured (always optional, the traveller can type their own);
without it the questions are still asked, just without suggested names.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.itinerary import ScopeResponse
from app.services.place_suggest_service import place_suggest_service
from app.utils.scope_defaults import static_scope
from app.utils.trip_planner import recommended_areas, scope_advice

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a careful travel planner. Reply with JSON only, no markdown. "
    "Only name real, well-known places. Never invent places. Keep each note under 10 words."
)


def _clean_items(raw: Any, exclude: str, limit: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = {exclude.strip().lower()}
    for it in raw if isinstance(raw, list) else []:
        name = str((it.get("name") if isinstance(it, dict) else it) or "").strip()
        note = str((it.get("note") if isinstance(it, dict) else "") or "").strip()
        if not name or len(name) > 60 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "note": note[:80]})
        if len(out) >= limit:
            break
    return out


def parse_scope_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
    except ValueError:
        # the model sometimes adds a sentence before or after the JSON: take the outermost {...}
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(cleaned[start:end + 1])
    return data if isinstance(data, dict) else {}


def build_scope(kind: str, name: str, days: int, ai: Optional[Dict[str, Any]], source: str = "") -> ScopeResponse:
    """Pure assembly of the response (the AI or built-in part is passed in), so it can be tested without a network."""
    ai = ai or {}
    modes: List[Dict[str, str]] = []
    suggestions: List[Dict[str, str]] = []
    neighbours: List[Dict[str, str]] = []
    s_title = n_title = ""
    if kind in ("city", "area"):
        modes = [{"value": "only", "label": f"Only {name}"},
                 {"value": "nearby", "label": f"{name} and nearby places"}]
        suggestions = _clean_items(ai.get("nearby"), name, 6)
        s_title = "Nearby places worth adding (optional)"
    elif kind == "state":
        modes = [{"value": "inside", "label": f"Stay inside {name}"},
                 {"value": "neighbours", "label": "Also explore neighbouring states"}]
        suggestions = _clean_items(ai.get("inside"), name, 8)
        s_title = f"Cities or areas in {name} you would like to visit (optional)"
        neighbours = _clean_items(ai.get("neighbours"), name, 5)
        n_title = "Neighbouring states to add (optional)"
    else:  # country
        suggestions = _clean_items(ai.get("inside"), name, 8)
        s_title = f"States or cities in {name} you would like to visit (optional, we choose if you skip)"
    big = kind in ("state", "country")
    gateway = str(ai.get("gateway") or "").strip() if big else ""
    if gateway.lower() == name.strip().lower():
        gateway = ""
    # Cities the traveller can start from: the suggested gateway first, then the other suggested places
    arrival_options: List[Dict[str, str]] = []
    if gateway:
        arrival_options.append({"name": gateway, "note": str(ai.get("gateway_note") or "best place to land")[:60]})
    for item in suggestions:
        if item["name"].lower() != gateway.lower() and len(arrival_options) < 6:
            arrival_options.append({"name": item["name"], "note": item.get("note", "")})
    return ScopeResponse(
        kind=kind, name=name, advice=scope_advice(kind, name, days), recommended_areas=recommended_areas(kind, days),
        modes=modes, suggestions=suggestions, suggestions_title=s_title, neighbours=neighbours, neighbours_title=n_title,
        needs_arrival=big, default_arrival=gateway or None, default_arrival_note=str(ai.get("gateway_note") or "") if gateway else "",
        arrival_options=arrival_options if big else [], source=source or ("ai" if ai else "basic"),
    )


class ScopeService:
    async def detect_kind(self, name: str, hint: Optional[str] = None) -> str:
        if hint in ("city", "state", "country", "area"):
            return hint
        key = name.split(",")[0].strip().lower()
        try:
            items, _ = await place_suggest_service.suggest(name, 8)
        except Exception:
            items = []
        for it in items:
            if it["name"].strip().lower() == key:
                return it["kind"]
        return "city"

    async def _ask_ai(self, kind: str, name: str, days: int) -> Optional[Dict[str, Any]]:
        if settings.MOCK_MODE or not settings.GEMINI_API_KEY:
            return None
        if kind in ("city", "area"):
            ask = ('Return {"nearby": [{"name": "...", "note": "..."}]} with up to 6 real towns or cities within about '
                   f'150 km of {name} that are worth a visit.')
        elif kind == "state":
            ask = (f'Return {{"gateway": "...", "inside": [...], "neighbours": [...]}} where "gateway" is the best city to land in '
                   f'or start from for {name} (usually its capital or the city with the main airport), "inside" lists up to 8 best '
                   f'cities or areas to base a trip in {name} and "neighbours" lists up to 4 neighbouring states or regions worth adding. '
                   'Each list item is {"name": "...", "note": "..."}.')
        else:
            ask = (f'Return {{"gateway": "...", "inside": [{{"name": "...", "note": "..."}}]}} where "gateway" is the best city to land in '
                   f'or start from in {name} (usually the capital or the city with the main international airport) and "inside" lists up to 8 '
                   f'of the best states, regions or cities to visit in {name} for a {days}-day trip.')
        try:
            from app.services.ai_service import ai_service
            text = await asyncio.wait_for(
                asyncio.to_thread(ai_service._generate_with_fallback, ask, _SYSTEM), timeout=25)
            return parse_scope_json(text)
        except Exception as exc:
            logger.info(f"Scope suggestions unavailable for '{name}': {exc}")
            return None

    async def scope(self, name: str, days: int, kind_hint: Optional[str] = None) -> ScopeResponse:
        clean = name.strip()
        short = clean.split(",")[0].strip() or clean
        kind = await self.detect_kind(clean, kind_hint)
        ai = await self._ask_ai(kind, short, days)
        builtin = static_scope(kind, short)
        if ai and (ai.get("inside") or ai.get("nearby")) and (ai.get("gateway") or kind in ("city", "area")):
            return build_scope(kind, short, days, ai, "ai")
        if ai and builtin:
            # the AI answered only in part: fill the gaps from the built-in list
            merged = {**builtin, **{k: v for k, v in ai.items() if v}}
            if ai.get("gateway") and str(ai["gateway"]).lower() != builtin["gateway"].lower():
                merged["gateway_note"] = ""  # the built-in note described a different city
            return build_scope(kind, short, days, merged, "ai")
        if builtin:
            return build_scope(kind, short, days, builtin, "static")
        return build_scope(kind, short, days, ai, "ai" if ai else "basic")


scope_service = ScopeService()
