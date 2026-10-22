"""24/7 Medical Care search API route."""

import asyncio
from fastapi import APIRouter, HTTPException, status
from app.models.medical import MedicalSearchRequest, MedicalSearchResponse
from app.services.geocoding_service import geocoding_service
from app.services.places_service import places_service

router = APIRouter(prefix="/api/medical", tags=["Medical"])


@router.post("/search", response_model=MedicalSearchResponse)
async def search_medical(req: MedicalSearchRequest):
    """Search medical facilities with verified 24/7 flags and emergency disclaimers."""
    try:
        center = await asyncio.to_thread(
            geocoding_service.resolve_center,
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
        response = await places_service.search_medical(
            center=center,
            service_types=req.service_types,
            radius_km=req.radius_km,
            limit=req.limit,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return response
