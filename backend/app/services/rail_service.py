"""Railway service with RailRadar provider abstraction (Section 7, 8, 31).
Provider is the source of truth for train schedules, fares, and operators.
Never invents train facts or booking URLs.
"""

import hashlib
import logging
import time
from typing import Optional, List, Dict, Any, Tuple
import httpx

from app.config import settings
from app.models.transport import TransportOption

logger = logging.getLogger(__name__)

# Common Indian Railway station codes
RAILWAY_STATION_MAP: Dict[str, str] = {
    "delhi": "NDLS",
    "new delhi": "NDLS",
    "amritsar": "ASR",
    "mumbai": "MMCT",
    "bombay": "CSMT",
    "goa": "MAO",
    "madgaon": "MAO",
    "bangalore": "SBC",
    "bengaluru": "SBC",
    "kolkata": "HWH",
    "howrah": "HWH",
    "chennai": "MAS",
    "hyderabad": "SC",
    "secunderabad": "SC",
    "jaipur": "JP",
    "ahmedabad": "ADI",
    "pune": "PUNE",
    "varanasi": "BSB",
    "lucknow": "LKO",
    "chandigarh": "CDG",
    "dehradun": "DDN",
    "haridwar": "HW",
    "rishikesh": "YNRK",
    "agra": "AGC",
    "mathura": "MTJ",
    "patna": "PNBE",
    "bhopal": "BPL",
    "indore": "INDB",
    "nagpur": "NGP",
    "guwahati": "GHY",
}


class RailRadarClient:
    """Official RailRadar API client abstraction."""
    BASE_URL = "https://api.railradar.in/v1"

    def __init__(self):
        pass

    def _get_api_key(self) -> Optional[str]:
        key = getattr(settings, "RAILRADAR_API_KEY", None)
        if not key or key.strip() in ("", "your_railradar_api_key_here"):
            return None
        return key.strip()

    async def _get_json(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 12.0) -> Dict[str, Any]:
        """GET helper shared by the lookup endpoints (key stays on the server)."""
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("RAILRADAR_API_KEY is not configured.")
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{self.BASE_URL}{path}", headers=headers, params=params or {})
        if response.status_code in (401, 403):
            raise RuntimeError("Invalid RAILRADAR_API_KEY: authentication failed with RailRadar.")
        if response.status_code == 429:
            raise RuntimeError("RailRadar rate limit reached.")
        if response.status_code == 404:
            return {"success": True, "data": None}
        if response.status_code >= 400:
            raise RuntimeError(f"RailRadar API error (HTTP {response.status_code}).")
        try:
            return response.json()
        except Exception:
            raise RuntimeError("Malformed response from RailRadar.")

    async def search_stations(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Station autocomplete (GET /v1/lookup/search/stations): codes, names and city."""
        return await self._get_json("/lookup/search/stations", {"q": query, "limit": limit})

    async def get_prs_directory(self) -> Dict[str, Any]:
        """All PRS-reserved trains with the classes each one carries (GET /v1/lookup/trains/prs)."""
        return await self._get_json("/lookup/trains/prs", timeout=25.0)

    async def get_trains_between_stations(
        self,
        from_code: str,
        to_code: str,
        date_str: str,
        timeout: float = 12.0
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            raise RuntimeError("RAILRADAR_API_KEY is not configured.")

        url = f"{self.BASE_URL}/trains/between/{from_code}/{to_code}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        params = {"date": date_str} if date_str else {}

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code == 401 or response.status_code == 403:
                raise RuntimeError("Invalid RAILRADAR_API_KEY: authentication failed with RailRadar.")
            elif response.status_code == 429:
                raise RuntimeError("RailRadar rate limit reached.")
            elif response.status_code == 404:
                # No trains / unknown station pair: not an error, just empty
                return {"success": True, "data": {"trains": []}}
            elif response.status_code >= 400:
                raise RuntimeError(f"RailRadar API error (HTTP {response.status_code}).")

            try:
                return response.json()
            except Exception:
                raise RuntimeError("Malformed response from RailRadar.")


_STATION_CACHE_TTL = 3600.0       # station names rarely change
_PRS_CACHE_TTL = 24 * 3600.0      # one big directory call per day keeps API usage tiny


class RailService:
    def __init__(self):
        self.client = RailRadarClient()
        self._station_cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}
        self._prs_cache: Optional[Tuple[float, Dict[str, Dict[str, Any]]]] = None

    # ------------------------------------------------------------------ stations
    @staticmethod
    def parse_station_results(data: Dict[str, Any], city_hint: str = "") -> List[Dict[str, str]]:
        """Normalises the autocomplete response and lists stations of the searched city first."""
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        out: List[Dict[str, str]] = []
        seen = set()
        for r in rows:
            if not isinstance(r, dict):
                continue
            code = str(r.get("code") or "").strip().upper()
            name = str(r.get("name") or "").strip()
            if not code or not name or code in seen:
                continue
            seen.add(code)
            out.append({"code": code, "name": name, "city": str(r.get("city") or "").strip()})
        hint = city_hint.strip().lower()
        if hint:
            out.sort(key=lambda x: 0 if x["city"].lower() == hint else 1)  # stable: keeps API order inside groups
        return out

    async def find_stations(self, query: str, limit: int = 20) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """Stations for a city or station name. Returns (stations, notice); never invents stations."""
        q = (query or "").strip()
        if len(q) < 2:
            return [], "Type at least 2 letters of the city or station name."
        key = f"{q.lower()}|{limit}"
        cached = self._station_cache.get(key)
        if cached and time.time() - cached[0] < _STATION_CACHE_TTL:
            return cached[1], None
        try:
            data = await self.client.search_stations(q, limit)
            stations = self.parse_station_results(data, q)
            if stations:
                self._station_cache[key] = (time.time(), stations)
            return stations, (None if stations else f"No railway stations found for '{q}'. Check the spelling.")
        except RuntimeError as exc:
            # Honest fallback: only the one station already known for this city, clearly labelled
            code = self.resolve_station_code(q)
            notice = f"Live station search unavailable ({exc})"
            if code:
                return [{"code": code, "name": f"{q.title()} (default main station)", "city": q.title()}], \
                    notice + ". Showing the default main station only."
            return [], notice
        except Exception as exc:
            logger.warning(f"RailRadar station search error: {exc}")
            return [], "Station search is temporarily unavailable."

    # ------------------------------------------------------------------ classes per train (verified)
    @staticmethod
    def parse_prs_directory(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for number, info in rows.items():
            if isinstance(info, dict) and isinstance(info.get("classes"), list):
                out[str(number)] = {
                    "classes": [str(c).strip().upper() for c in info["classes"]],
                    "type": info.get("type"),
                    "name": info.get("name"),
                }
        return out

    async def get_train_classes(self) -> Dict[str, Dict[str, Any]]:
        """{train_number: {'classes': ['1A','2A','3A'], ...}} from RailRadar (cached for a day)."""
        if self._prs_cache and time.time() - self._prs_cache[0] < _PRS_CACHE_TTL:
            return self._prs_cache[1]
        data = await self.client.get_prs_directory()
        directory = self.parse_prs_directory(data)
        if directory:
            self._prs_cache = (time.time(), directory)
        return directory

    def resolve_station_code(self, city_or_station: str) -> Optional[str]:
        clean = city_or_station.strip()
        if len(clean) in (3, 4) and clean.isalpha() and clean.isupper():
            return clean

        # 'Amritsar, Punjab, India' -> 'amritsar'
        lower = " ".join(clean.split(",")[0].strip().lower().split())
        # Exact match only: never guess a station from a partial name
        return RAILWAY_STATION_MAP.get(lower)

    async def resolve_station_code_live(self, city: str) -> Optional[str]:
        """Built-in list first; otherwise the main station RailRadar knows for exactly this city name.

        Cities outside India (or unknown ones) simply return None: trains cover India only.
        """
        code = self.resolve_station_code(city)
        if code:
            return code
        key = " ".join(city.split(",")[0].strip().lower().split())
        if not key:
            return None
        try:
            stations, _ = await self.find_stations(key, 10)
        except Exception:
            return None
        for s in stations:
            if (s.get("city") or "").strip().lower() == key:
                return s["code"]
        return None

    def parse_railradar_response(
        self,
        data: Dict[str, Any],
        from_stn: str,
        to_stn: str,
        currency: str = "INR"
    ) -> List[TransportOption]:
        """Normalizes RailRadar /v1/trains/between response into TransportOption items.

        Documented shape: {"data": {"trains": [{"train": {number, name, type},
        "from": {departure}, "to": {arrival}, "duration": minutes,
        "totalHaltsBetween": n}]}}. RailRadar returns no fare or booking URL,
        so price and booking_url stay None (never invented).
        """
        payload = data.get("data") if isinstance(data, dict) else None
        trains_list = (payload or {}).get("trains") if isinstance(payload, dict) else None
        if not isinstance(trains_list, list):
            return []

        options: List[TransportOption] = []
        for t in trains_list:
            if not isinstance(t, dict):
                continue
            tr = t.get("train") or {}
            frm = t.get("from") or {}
            to = t.get("to") or {}
            train_num = str(tr.get("number") or "")
            train_name = tr.get("name") or "Train"
            dep_time = frm.get("departure") or ""
            arr_time = to.get("arrival") or ""
            try:
                duration_min = int(t.get("duration") or 0)
            except (TypeError, ValueError):
                duration_min = 0
            if not dep_time or not arr_time:
                continue

            dur_h, dur_m = divmod(duration_min, 60)
            dur_formatted = f"{dur_h}h {dur_m}m" if dur_h > 0 else f"{dur_m}m"
            key = f"{train_num}_{dep_time}_{from_stn}_{to_stn}"
            option_id = f"trn_{train_num}_{hashlib.sha1(key.encode()).hexdigest()[:8]}"

            options.append(TransportOption(
                id=option_id,
                mode="train",
                provider="railradar",
                operator=f"Indian Railways ({train_name})",
                number=train_num,
                origin=f"{from_stn} Station",
                destination=f"{to_stn} Station",
                departure_time=dep_time,
                arrival_time=arr_time,
                duration_minutes=duration_min,
                duration_formatted=dur_formatted,
                stops=int(t.get("totalHaltsBetween") or 0),
                price=None,
                currency=currency,
                cabin_or_class=None,
                booking_url=None,
                raw_provider_data={
                    "train_type": tr.get("type"),
                    "run_days": tr.get("runDays"),
                    "distance_km": t.get("distance"),
                    "arrival_day_offset": to.get("day"),
                },
            ))

        return options

    async def search_trains(
        self,
        from_city: str,
        to_city: str,
        date_str: str,
        currency: str = "INR",
        from_code: Optional[str] = None,
        to_code: Optional[str] = None,
    ) -> Tuple[List[TransportOption], Optional[str]]:
        """Searches trains for route and date. Returns (options, notice).

        from_code / to_code are the stations the traveller picked; without them the
        city name is matched against the built-in station list.
        """
        from_code = from_code or await self.resolve_station_code_live(from_city)
        to_code = to_code or await self.resolve_station_code_live(to_city)

        for city, code in ((from_city, from_code), (to_city, to_code)):
            if not code:
                return [], (f"No Indian railway station found for '{city.strip()}'. "
                            "Train search covers stations in India only.")

        try:
            data = await self.client.get_trains_between_stations(from_code, to_code, date_str)
            options = self.parse_railradar_response(data, from_code, to_code, currency=currency)
            return options, None
        except RuntimeError as exc:
            err = str(exc)
            logger.info(f"RailRadar notice: {err}")
            return [], err
        except Exception as exc:
            logger.warning(f"RailRadar search error: {exc}")
            return [], f"Train schedule service temporarily unavailable ({str(exc)})."


rail_service = RailService()
