"""Area Guide / Summarizer API route.

In live mode (MOCK_MODE=false):
1. Geocodes the area via Geoapify
2. Fetches nearby places from Geoapify
3. Passes verified places to Gemini for area summarization
4. Returns the structured area guide
"""

import asyncio
from typing import Any, Dict, List, Optional
from app.security import require_user_or_guest
from fastapi import APIRouter, HTTPException, status, Depends
from app.config import settings
from app.models.area import AreaSummarizeRequest, AreaSummarizeResponse
from app.services.ai_service import ai_service
from app.services.geocoding_service import geocoding_service
from app.services.places_service import _fetch_geoapify_places, _geoapify_feature_to_dict, _PLACES_CATEGORIES

router = APIRouter(prefix="/api/area", tags=["Area Guide"])


@router.post("/summarize", response_model=AreaSummarizeResponse, dependencies=[Depends(require_user_or_guest)])
async def summarize_area(req: AreaSummarizeRequest):
    """Summarize an urban area with distinct analytical sections."""
    verified_places: Optional[List[Dict[str, Any]]] = None

    if not settings.MOCK_MODE:
        # Step 1: Geocode area
        try:
            center = await asyncio.to_thread(geocoding_service.resolve_center, location=req.area)
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

        # Step 2: Fetch verified places from Geoapify
        try:
            radius_m = int(req.radius_km * 1000)
            features = _fetch_geoapify_places(
                center.latitude, center.longitude,
                radius_m, _PLACES_CATEGORIES, limit=40,
            )
            raw_places = [_geoapify_feature_to_dict(f) for f in features]
            verified_places = [
                {
                    "name": p["name"],
                    "address": p.get("address"),
                    "category": p.get("category", "general"),
                }
                for p in raw_places
                if p.get("name") and p["name"].strip()
                and p["name"].strip().lower() not in (
                    "unnamed place", "unknown", "unnamed road", "n/a", "null"
                )
            ]
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

    # Step 3: Generate area guide
    try:
        response = await ai_service.summarize_area(req, verified_places=verified_places)
        return response
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to summarize area: {str(exc)}",
        )
