"""Transport search service orchestrating multi-modal searches for Outbound and Return legs (Section 6, 7, 8, 9, 31).
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import List, Optional
from app.models.transport import (
    FlightDatePrice,
    FlightDatesResponse,
    TransportSearchRequest,
    TransportSearchResponse,
    TransportLegResult,
    TransportOption
)
from app.services.flight_service import flight_service
from app.services.rail_service import rail_service
from app.services.train_advisor_service import train_advisor_service
from app.services.train_fare_service import train_fare_service
from app.services.transport_recommendation_service import transport_recommendation_service
from app.utils.price_tiers import build_date_note, classify_price_tiers, pretty_date

NEARBY_DAYS = 2  # show the 2 days before and the 2 days after the chosen date

logger = logging.getLogger(__name__)


class TransportSearchService:
    async def _search_leg(
        self,
        origin: str,
        destination: str,
        date_str: str,
        travelers: int,
        preference: str,
        currency: str,
        train_classes: Optional[List[str]] = None,
        from_code: Optional[str] = None,
        to_code: Optional[str] = None,
    ) -> TransportLegResult:
        """Searches both flights and trains concurrently for a single one-way leg."""
        # Always quote ONE adult so every price shown is per person; totals multiply later.
        flight_task = flight_service.search_flights(
            origin, destination, date_str, adults=1, currency=currency
        )
        rail_task = rail_service.search_trains(
            origin, destination, date_str, currency=currency, from_code=from_code, to_code=to_code
        )

        flight_res, rail_res = await asyncio.gather(
            flight_task, rail_task, return_exceptions=True
        )

        flights, apt_notice = ([], None)
        if isinstance(flight_res, tuple):
            flights, apt_notice = flight_res
        elif isinstance(flight_res, Exception):
            logger.warning(f"Flight search error: {flight_res}")
            apt_notice = f"Flights unavailable: {str(flight_res)}"

        trains, rail_notice = ([], None)
        if isinstance(rail_res, tuple):
            trains, rail_notice = rail_res
        elif isinstance(rail_res, Exception):
            logger.warning(f"Train search error: {rail_res}")
            rail_notice = f"Trains unavailable: {str(rail_res)}"

        # Fare & availability for the chosen classes (verified data only), then train advice
        train_advice = None
        if trains:
            try:
                fa_notice = await train_fare_service.enrich(
                    trains, train_classes or [], from_code, to_code, date_str
                )
                if fa_notice and train_classes:
                    rail_notice = f"{rail_notice} {fa_notice}".strip() if rail_notice else fa_notice
                train_advice = await train_advisor_service.advise(trains, train_classes or [], preference)
            except Exception as exc:  # extras must never break the basic search
                logger.warning(f"Train fare/advice step failed: {exc}")

        # Combine all options for composite recommendation scoring
        all_options = flights + trains
        scored = transport_recommendation_service.score_options(all_options, preference=preference)
        top_rec = scored[0] if scored else None

        # Re-separate scored options preserving their score ranking
        scored_flights = [o for o in scored if o.mode == "flight"]
        scored_trains = [o for o in scored if o.mode == "train"]

        return TransportLegResult(
            flights=scored_flights,
            trains=scored_trains,
            top_recommendation=top_rec,
            airport_notice=apt_notice,
            rail_notice=rail_notice,
            train_advice=train_advice
        )

    async def search_transport(self, req: TransportSearchRequest) -> TransportSearchResponse:
        """Searches outbound and optional return transport legs independently."""
        outbound_task = self._search_leg(
            req.source,
            req.destination,
            req.outbound_date,
            req.travelers,
            req.preference,
            req.currency,
            req.train_classes,
            req.source_station_code,
            req.destination_station_code,
        )

        return_task = None
        if req.return_date:
            return_task = self._search_leg(
                req.destination,
                req.source,
                req.return_date,
                req.travelers,
                req.preference,
                req.currency,
                req.train_classes,
                req.destination_station_code,
                req.source_station_code,
            )

        if return_task:
            outbound_res, return_res = await asyncio.gather(outbound_task, return_task)
        else:
            outbound_res = await outbound_task
            return_res = None

        return TransportSearchResponse(
            source=req.source,
            destination=req.destination,
            outbound=outbound_res,
            return_leg=return_res,
            preference=req.preference
        )


    async def search_one_leg(self, origin: str, destination: str, date_str: str, travelers: int,
                             preference: str, currency: str, train_classes: Optional[List[str]] = None,
                             from_code: Optional[str] = None, to_code: Optional[str] = None) -> TransportLegResult:
        """Public wrapper used when the traveller switches one leg to a nearby date."""
        return await self._search_leg(origin, destination, date_str, travelers, preference, currency,
                                      train_classes, from_code, to_code)

    async def flight_date_prices(self, origin: str, destination: str, date_str: str, travelers: int,
                                 currency: str, earliest_date: Optional[str] = None) -> FlightDatesResponse:
        """Cheapest flight per day for the chosen date and the 2 days either side.

        Prices are real Google Flights quotes (SerpApi). A day with no result stays 'unknown'.
        """
        centre = date.fromisoformat(date_str)
        earliest = date.fromisoformat(earliest_date) if earliest_date else None
        today = date.today()
        wanted = []
        for offset in range(-NEARBY_DAYS, NEARBY_DAYS + 1):
            d = centre + timedelta(days=offset)
            if d < today or (earliest and d < earliest):
                continue
            wanted.append(d)

        async def one(d: date):
            try:
                flights, notice = await flight_service.search_flights(
                    origin, destination, d.isoformat(), adults=1, currency=currency
                )
                return d, flights, notice, None
            except Exception as exc:
                logger.info(f"Nearby-date flight search failed for {d}: {exc}")
                return d, [], None, str(exc)

        results = await asyncio.gather(*(one(d) for d in wanted))
        notice = next((n for _, _, n, _ in results if n), None)
        errors = [e for _, _, _, e in results if e]

        entries = []
        for d, flights, _, _ in results:
            prices = [f.price for f in flights if f.price and f.price > 0]
            entries.append({
                "date": d.isoformat(),
                "cheapest_price": min(prices) if prices else None,
                "flights_found": len(flights),
            })
        logger.info("Nearby flight prices %s->%s: %s", origin, destination,
                    ", ".join(f"{e['date']}={e['cheapest_price']}({e['flights_found']} flights)" for e in entries))
        tiers = classify_price_tiers({e["date"]: e["cheapest_price"] for e in entries})
        priced = [e["cheapest_price"] for e in entries if e["cheapest_price"]]
        cheapest_val = min(priced) if priced else None
        days = [
            FlightDatePrice(
                date=e["date"],
                label=pretty_date(e["date"]),
                cheapest_price=e["cheapest_price"],
                tier=tiers[e["date"]],
                flights_found=e["flights_found"],
                is_selected=(e["date"] == date_str),
                is_cheapest=(cheapest_val is not None and e["cheapest_price"] == cheapest_val and len(priced) > 1),
            )
            for e in entries
        ]
        if not priced and errors and not notice:
            notice = "Nearby-date prices could not be loaded right now."
        return FlightDatesResponse(
            days=days,
            note=build_date_note(entries, date_str),
            notice=notice,
            currency=currency,
        )


transport_search_service = TransportSearchService()
