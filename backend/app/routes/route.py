"""Route endpoint implementing Section 50.7 specifications.
"""

from fastapi import APIRouter, HTTPException, status
from app.models.route import RouteRequest, RouteResponse
from app.services.routing_service import routing_service

router = APIRouter(prefix="/api/route", tags=["Routing"])


@router.post("", response_model=RouteResponse)
async def compute_route(req: RouteRequest):
    """Compute walking or driving route between two points,
    or return approximate straight line if routing service is unavailable.
    """
    try:
        route = await routing_service.get_route(
            origin_lat=req.origin.latitude,
            origin_lon=req.origin.longitude,
            dest_lat=req.destination.latitude,
            dest_lon=req.destination.longitude,
            mode=req.mode
        )
        return route
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to process route calculation: {str(exc)}"
        )
