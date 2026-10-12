"""Railway service with RailRadar provider abstraction (Section 7, 8, 31).
Provider is the source of truth for train schedules, fares, and operators.
Never invents train facts or booking URLs.
"""

import hashlib
import logging
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


class RailService:
    def __init__(self):
        self.client = RailRadarClient()

    def resolve_station_code(self, city_or_station: str) -> Optional[str]:
        clean = city_or_station.strip()
        if len(clean) in (3, 4) and clean.isalpha() and clean.isupper():
            return clean

        lower = clean.lower()
        # Exact match only: never guess a station from a partial name
        return RAILWAY_STATION_MAP.get(lower)

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
        currency: str = "INR"
    ) -> Tuple[List[TransportOption], Optional[str]]:
        """Searches trains for route and date. Returns (options, notice)."""
        from_code = self.resolve_station_code(from_city)
        to_code = self.resolve_station_code(to_city)

        if not from_code:
            return [], f"Railway station code for '{from_city}' could not be identified."
        if not to_code:
            return [], f"Railway station code for '{to_city}' could not be identified."

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
