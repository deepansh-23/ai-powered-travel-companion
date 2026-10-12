"""Itinerary planner API route.

In live mode (MOCK_MODE=false), this route:
1. Geocodes the destination via Geoapify
2. Fetches nearby places from Geoapify (using the user's radius)
3. Passes verified places to Gemini for itinerary organization
4. Returns the result to the frontend
Never silently falls back to Manchester mock data in live mode.
"""

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.itinerary import ItineraryRequest, ItineraryResponse
from app.services.ai_service import ai_service
from app.services.geocoding_service import geocoding_service
from app.services.places_service import (
    _PLACES_CATEGORIES,
    _fetch_geoapify_places,
    _geoapify_feature_to_dict,
)
from app.security import require_user
from app.services.directions_service import enrich_itinerary
from fastapi import APIRouter, HTTPException, status, Depends

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/itinerary", tags=["Itinerary"])


@router.post("/generate", response_model=ItineraryResponse, dependencies=[Depends(require_user)])
async def generate_itinerary(req: ItineraryRequest):
  """Generate a multi-day personalized itinerary."""
  verified_places: Optional[List[Dict[str, Any]]] = None

  if not settings.MOCK_MODE:
    # Step 1: Geocode destination
    try:
      center = geocoding_service.resolve_center(location=req.destination)
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
          center.latitude,
          center.longitude,
          radius_m,
          _PLACES_CATEGORIES,
          limit=40,
      )
      raw_places = [_geoapify_feature_to_dict(f) for f in features]
      verified_places = [
          {
              "name": p["name"],
              "address": p.get("address"),
              "category": p.get("category", "general"),
              "latitude": p.get("latitude"),
              "longitude": p.get("longitude"),
              "website": p.get("website"),
          }
          for p in raw_places
          if p.get("name")
          and p["name"].strip()
          and p["name"].strip().lower()
          not in ("unnamed place", "unknown", "unnamed road", "n/a", "null")
      ]
    except Exception as exc:
      logger.warning(f"Failed to fetch Geoapify places: {exc}")
      raise HTTPException(
          status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
          detail=(
              "Could not fetch real places for this destination from Geoapify."
              " Please retry; no itinerary was generated to avoid invented places."
          ),
      )

    if not verified_places:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=(
              f"No real places were found near '{req.destination}'."
              " Try a larger radius or a different destination."
          ),
      )

  # Step 3: Generate itinerary via Gemini or mock engine
  try:
    response = await ai_service.generate_itinerary(
        req, verified_places=verified_places
    )
    try:
      enrich_itinerary(response, req, verified_places)
    except Exception as exc:  # directions are a bonus: never fail the itinerary
      logger.warning(f"Could not add stop-to-stop directions: {exc}")
    return response
  except (ValueError, RuntimeError) as exc:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(exc),
    )
  except Exception as exc:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to generate itinerary: {str(exc)}",
    )