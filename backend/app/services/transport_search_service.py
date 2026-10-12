"""Transport search service orchestrating multi-modal searches for Outbound and Return legs (Section 6, 7, 8, 9, 31).
"""

import asyncio
import logging
from typing import Optional
from app.models.transport import (
    TransportSearchRequest,
    TransportSearchResponse,
    TransportLegResult,
    TransportOption
)
from app.services.flight_service import flight_service
from app.services.rail_service import rail_service
from app.services.transport_recommendation_service import transport_recommendation_service

logger = logging.getLogger(__name__)


class TransportSearchService:
    async def _search_leg(
        self,
        origin: str,
        destination: str,
        date_str: str,
        travelers: int,
        preference: str,
        currency: str
    ) -> TransportLegResult:
        """Searches both flights and trains concurrently for a single one-way leg."""
        flight_task = flight_service.search_flights(
            origin, destination, date_str, adults=travelers, currency=currency
        )
        rail_task = rail_service.search_trains(
            origin, destination, date_str, currency=currency
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
            rail_notice=rail_notice
        )

    async def search_transport(self, req: TransportSearchRequest) -> TransportSearchResponse:
        """Searches outbound and optional return transport legs independently."""
        outbound_task = self._search_leg(
            req.source,
            req.destination,
            req.outbound_date,
            req.travelers,
            req.preference,
            req.currency
        )

        return_task = None
        if req.return_date:
            return_task = self._search_leg(
                req.destination,
                req.source,
                req.return_date,
                req.travelers,
                req.preference,
                req.currency
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


transport_search_service = TransportSearchService()
