"""Quiet Work Cafes search API route."""

from fastapi import APIRouter, HTTPException, status
from app.models.cafes import CafesSearchRequest, CafesSearchResponse
from app.services.geocoding_service import geocoding_service
from app.services.places_service import places_service

router = APIRouter(prefix="/api/cafes", tags=["Cafes"])


@router.post("/search", response_model=CafesSearchResponse)
async def search_cafes(req: CafesSearchRequest):
    """Search work-friendly cafes near location with amenity filters."""
    try:
        center = geocoding_service.resolve_center(
            location=req.location,
            latitude=req.latitude,
            longitude=req.longitude,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    try:
        response = await places_service.search_cafes(
            center=center,
            amenities=req.amenities,
            radius_km=req.radius_km,
            limit=req.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return response
