"""Hotel API routes for discovery, sorting, and price comparison (Section 7A, 31).
"""

from datetime import date
from typing import List, Dict, Any
from app.security import require_user
from fastapi import APIRouter, HTTPException, status, Depends
from app.models.hotel import (
    HotelSearchRequest,
    HotelSearchResponse,
    HotelDetailsRequest,
    HotelPriceSource
)
from app.services.hotel_service import hotel_service

router = APIRouter(prefix="/api/hotel", tags=["Hotels"])


def validate_hotel_search(req: HotelSearchRequest):
    dst = req.destination.strip()
    if not dst or len(dst) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Destination must be at least 2 characters long."
        )

    try:
        cin = date.fromisoformat(req.check_in_date)
        cout = date.fromisoformat(req.check_out_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-in and check-out dates must be valid ISO YYYY-MM-DD format."
        )

    today = date.today()
    if cin < today:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-in date cannot be in the past."
        )

    if cout < cin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Check-out date cannot be before check-in date."
        )

    if req.travelers < 1 or req.travelers > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Number of travellers must be between 1 and 20."
        )


@router.post("/search", response_model=HotelSearchResponse, dependencies=[Depends(require_user)])
async def search_hotels(req: HotelSearchRequest):
    """Search hotels for the specified destination and stay duration."""
    validate_hotel_search(req)
    try:
        hotels = await hotel_service.search_hotels(req)
        return HotelSearchResponse(
            destination=req.destination,
            check_in_date=req.check_in_date,
            check_out_date=req.check_out_date,
            hotels=hotels,
            total_found=len(hotels)
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hotel search failed: {str(exc)}"
        )


@router.post("/details", response_model=Dict[str, Any], dependencies=[Depends(require_user)])
async def get_hotel_details(req: HotelDetailsRequest):
    """Retrieve full booking-site price comparison on-demand for a selected hotel."""
    if not req.property_token or not req.property_token.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Property token is required to fetch hotel details."
        )

    try:
        sources = await hotel_service.get_hotel_property_details(
            property_token=req.property_token.strip(),
            check_in_date=req.check_in_date,
            check_out_date=req.check_out_date,
            currency=req.currency,
            adults=req.adults
        )
        return {
            "property_token": req.property_token,
            "price_sources": [s.model_dump() for s in sources]
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch hotel details: {str(exc)}"
        )
