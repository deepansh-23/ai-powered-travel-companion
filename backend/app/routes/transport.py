"""Transport API routes for multi-modal travel search (Section 6, 7, 9, 31).
Validates source, destination, dates, and travelers strictly.
"""

from datetime import date
from typing import Any, Dict, List, Optional
from app.security import require_user
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.models.transport import TransportSearchRequest, TransportSearchResponse
from app.services.transport_search_service import transport_search_service
from app.services.flight_service import flight_service

router = APIRouter(prefix="/api/transport", tags=["Transport"])


def validate_transport_request(req: TransportSearchRequest):
    """Enforces Section 5 & Section 33A validation rules."""
    src = req.source.strip()
    dst = req.destination.strip()

    if not src or len(src) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Source location must be at least 2 characters long."
        )

    if not dst or len(dst) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Destination location must be at least 2 characters long."
        )

    # Check identical source and destination
    if src.lower() == dst.lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Source and destination cannot be the same city. Please select different locations."
        )

    # Validate dates
    try:
        dep_date = date.fromisoformat(req.outbound_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Outbound date must be a valid date in YYYY-MM-DD format."
        )

    # Past date validation
    today = date.today()
    if dep_date < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Outbound departure date cannot be in the past."
        )

    if req.return_date:
        try:
            ret_date = date.fromisoformat(req.return_date)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Return date must be a valid date in YYYY-MM-DD format."
            )

        if ret_date < dep_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Return date cannot be before outbound departure date."
            )

    if req.travelers < 1 or req.travelers > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Number of travellers must be between 1 and 20."
        )


@router.post("/search", response_model=TransportSearchResponse, dependencies=[Depends(require_user)])
async def search_transport(req: TransportSearchRequest):
    """Search outbound and return flights and trains with deterministic comparison."""
    validate_transport_request(req)
    try:
        response = await transport_search_service.search_transport(req)
        return response
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transport search encountered an unexpected error: {str(exc)}"
        )


class FlightBookingRequest(BaseModel):
    booking_token: str
    search_params: Dict[str, Any] = {}


_ALLOWED_BOOKING_PARAMS = {"departure_id", "arrival_id", "outbound_date", "adults", "currency"}


@router.post("/flight-booking", dependencies=[Depends(require_user)])
async def flight_booking_options(req: FlightBookingRequest):
    """Return provider-supplied booking options for a selected flight (Section 11).

    No booking or payment happens in-app; the frontend sends the user to the
    provider-supplied link. Only whitelisted search parameters are accepted.
    """
    if not req.booking_token.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="booking_token is required.",
        )
    params = {k: v for k, v in req.search_params.items() if k in _ALLOWED_BOOKING_PARAMS}
    missing = {"departure_id", "arrival_id", "outbound_date"} - set(params)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing search parameters: {', '.join(sorted(missing))}",
        )
    try:
        options = await flight_service.get_booking_options(req.booking_token.strip(), params)
        return {"options": options}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not fetch booking options: {str(exc)}",
        )
