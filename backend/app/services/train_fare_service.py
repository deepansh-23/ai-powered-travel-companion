"""Fare & availability for trains: verified data only, never invented.

What RailRadar can and cannot tell us (checked against its public API docs):
  * It DOES say which classes (1A / 2A / 3A / SL ...) each reserved train carries.
  * It does NOT provide fares or seat availability (Available / RAC / Waiting list).

So for RailRadar-backed results this service reports, per selected class:
  - whether the train carries the class (verified),
  - fare and availability as "not provided" (None), never a guess.
The provider interface below lets a fare/availability source be plugged in later
(IRCTC partner API, etc.). Only trains that carry a selected class are ever sent to
such a provider, and only for those classes, to keep API usage low.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from app.models.transport import (
    TRAIN_CLASS_LABELS,
    TrainClassInfo,
    TrainFareAvailability,
    TransportOption,
)
from app.services.rail_service import rail_service

logger = logging.getLogger(__name__)

IRCTC_CHECK_URL = "https://www.irctc.co.in/nget/train-search"  # official site, no made-up deep link
MAX_TRAINS_FOR_PROVIDER_LOOKUPS = 10

_WL_WORDS = ("WL", "WAITING", "GNWL", "RLWL", "PQWL", "RSWL", "TQWL", "CKWL", "RLGN")


def normalize_availability(text: Optional[str]) -> Optional[str]:
    """Provider text -> 'AVAILABLE' | 'RAC' | 'WL' | None (unknown).

    'AVAILABLE-0045', 'Available 45' -> AVAILABLE;  'RAC 12', 'RAC/23' -> RAC;
    'GNWL 12/WL 8', 'WL 5', 'Waiting list' -> WL.  Anything else is None.
    """
    if not text:
        return None
    t = str(text).strip().upper()
    if t.startswith("AVAILABLE") or t.startswith("AVL") or re.match(r"^CURR_AVBL|^CURRENT", t):
        return "AVAILABLE"
    if t.startswith("RAC"):
        return "RAC"
    if any(t.startswith(w) or f" {w}" in t for w in _WL_WORDS):
        return "WL"
    return None


class ClassQuote:
    """What a provider returned for one train + class."""

    def __init__(self, fare_per_person: Optional[float] = None, availability_text: Optional[str] = None):
        self.fare_per_person = fare_per_person
        self.availability_text = availability_text


class FareProvider:
    name = "none"
    supports_fares = False
    supports_availability = False

    async def fetch(self, train: TransportOption, class_code: str, from_code: str, to_code: str,
                    date_str: str) -> Optional[ClassQuote]:  # pragma: no cover - interface
        return None


class RailRadarFareProvider(FareProvider):
    """RailRadar has no fare / availability endpoint, so this provider never makes a call."""

    name = "railradar"
    supports_fares = False
    supports_availability = False


class TrainFareService:
    def __init__(self, provider: Optional[FareProvider] = None):
        self.provider = provider or RailRadarFareProvider()

    async def enrich(
        self,
        trains: List[TransportOption],
        selected_classes: List[str],
        from_code: Optional[str],
        to_code: Optional[str],
        date_str: str,
    ) -> Optional[str]:
        """Attaches `fare_availability` to each train. Returns a notice for the user (or None).

        Nothing happens when the traveller chose no classes (the section is optional).
        """
        if not trains or not selected_classes:
            return None

        # 1) Which classes does each train carry? One cached directory call, not one per train.
        directory: Dict[str, Dict[str, Any]] = {}
        classes_verified = True
        notice: Optional[str] = None
        try:
            directory = await rail_service.get_train_classes()
            if not directory:
                classes_verified = False
                notice = "RailRadar returned no class information, so classes could not be verified."
        except RuntimeError as exc:
            classes_verified = False
            notice = f"Class information unavailable ({exc})."
        except Exception as exc:  # network etc.
            logger.warning(f"PRS class lookup failed: {exc}")
            classes_verified = False
            notice = "Class information is temporarily unavailable."

        # 2) Build per-train, per-class rows from verified data only.
        for t in trains:
            info = directory.get(str(t.number or "")) if classes_verified else None
            carried = set(info["classes"]) if info else None
            rows: List[TrainClassInfo] = []
            for code in selected_classes:
                label = TRAIN_CLASS_LABELS[code]
                if carried is None:
                    offered, quality, note = None, "unavailable", "Could not verify whether this train has this class."
                else:
                    offered = code in carried
                    quality = "verified"
                    note = None if offered else "This train does not have this class."
                rows.append(TrainClassInfo(code=code, label=label, offered=offered, data_quality=quality, note=note))
            t.fare_availability = TrainFareAvailability(
                classes=rows,
                fares_supported=self.provider.supports_fares,
                availability_supported=self.provider.supports_availability,
                classes_verified=carried is not None,
                source=self.provider.name,
                check_url=IRCTC_CHECK_URL,
                notice=None,
            )

        # 3) Fares / availability only when a provider supports them, only for relevant trains + classes.
        if self.provider.supports_fares or self.provider.supports_availability:
            await self._fill_from_provider(trains, from_code or "", to_code or "", date_str)
        else:
            msg = ("Fares and seat availability (Available / RAC / Waiting list) are not provided by RailRadar, "
                   "so none are shown here rather than guessing. Check IRCTC for live fares and availability.")
            for t in trains:
                if t.fare_availability:
                    t.fare_availability.notice = msg
            notice = f"{notice} {msg}".strip() if notice else msg
        return notice

    async def _fill_from_provider(self, trains: List[TransportOption], from_code: str, to_code: str,
                                  date_str: str) -> None:
        relevant = [t for t in trains if t.fare_availability and any(c.offered for c in t.fare_availability.classes)]
        relevant = relevant[:MAX_TRAINS_FOR_PROVIDER_LOOKUPS]
        jobs = []
        for t in relevant:
            for c in t.fare_availability.classes:
                if c.offered:
                    jobs.append((t, c))

        async def run(t, c):
            try:
                return await self.provider.fetch(t, c.code, from_code, to_code, date_str)
            except Exception as exc:
                logger.info(f"Fare lookup failed for {t.number}/{c.code}: {exc}")
                return None

        results = await asyncio.gather(*(run(t, c) for t, c in jobs))
        for (t, c), quote in zip(jobs, results):
            if quote is None:
                c.note = "Fare/availability not returned for this class."
                continue
            if self.provider.supports_fares and quote.fare_per_person and quote.fare_per_person > 0:
                c.fare_per_person = float(quote.fare_per_person)
            if self.provider.supports_availability:
                status = normalize_availability(quote.availability_text)
                if status:
                    c.availability_status = status
                    c.availability_detail = quote.availability_text
            if c.fare_per_person is not None or c.availability_status is not None:
                c.data_quality = "verified"


train_fare_service = TrainFareService()
