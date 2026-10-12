"""Places search API route."""

from fastapi import APIRouter, HTTPException, status
from app.models.places import PlacesSearchRequest, PlacesSearchResponse
from app.services.geocoding_service import geocoding_service
from app.services.places_service import places_service

router = APIRouter(prefix="/api/places", tags=["Places"])


@router.post("/search", response_model=PlacesSearchResponse)
async def search_places(req: PlacesSearchRequest):
    """Search places near a center or typed location."""
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
        response = await places_service.search_places(
            center=center,
            categories=req.categories,
            radius_km=req.radius_km,
            limit=req.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    if response.total == 0:
        # Don't raise — return the empty response so the frontend can show the right message
        pass

    return response
