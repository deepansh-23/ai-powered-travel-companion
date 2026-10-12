"""Hotel service integrating SerpApi Google Hotels engine (Section 7A, 8, 31).
Discovers hotels, compares prices across booking sites, and retrieves provider booking links.
Never fabricates hotel prices, ratings, or availability.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.hotel import HotelOption, HotelPriceSource, HotelSearchRequest
from app.services.hotel_recommendation_service import (
    hotel_recommendation_service,
)
from app.services.serpapi_client import serpapi_client

logger = logging.getLogger(__name__)


class HotelService:

  def _extract_number(self, val: Any) -> Optional[float]:
    if val is None:
      return None
    if isinstance(val, (int, float)):
      return float(val)
    if isinstance(val, str):
      digits = re.sub(r"[^\d.]", "", val)
      try:
        return float(digits) if digits else None
      except Exception:
        return None
    return None

  def parse_serpapi_hotels(
      self,
      data: Dict[str, Any],
      check_in_date: str,
      check_out_date: str,
      currency: str = "INR",
  ) -> List[HotelOption]:
    """Normalizes SerpApi Google Hotels properties response."""
    properties = data.get("properties", [])
    if not isinstance(properties, list):
      return []

    hotels: List[HotelOption] = []
    seen_ids = set()

    for p in properties:
      name = p.get("name")
      if not name or not name.strip():
        continue

      hotel_id = p.get("property_token") or f"htl_{hashlib.sha1(name.encode()).hexdigest()[:10]}"
      if hotel_id in seen_ids:
        continue
      seen_ids.add(hotel_id)

      # Coordinates
      gps = p.get("gps_coordinates", {})
      lat = gps.get("latitude")
      lon = gps.get("longitude")

      # Rating & Reviews
      rating = p.get("overall_rating")
      if rating is not None:
        try:
          rating = round(float(rating), 1)
        except Exception:
          rating = None
      review_count = p.get("reviews")
      if review_count is not None:
        try:
          review_count = int(review_count)
        except Exception:
          review_count = None

      # Star Class
      hotel_class = p.get("extracted_hotel_class")
      if hotel_class is None:
        class_str = str(p.get("hotel_class", ""))
        match = re.search(r"(\d+)", class_str)
        if match:
          hotel_class = int(match.group(1))

      # Prices
      rate_per_night = p.get("rate_per_night", {})
      nightly_price = None
      if isinstance(rate_per_night, dict):
        nightly_price = self._extract_number(
            rate_per_night.get("extracted_lowest")
            or rate_per_night.get("lowest")
        )
      elif isinstance(rate_per_night, (int, float, str)):
        nightly_price = self._extract_number(rate_per_night)

      total_rate = p.get("total_rate", {})
      total_price = None
      if isinstance(total_rate, dict):
        total_price = self._extract_number(
            total_rate.get("extracted_lowest") or total_rate.get("lowest")
        )
      elif isinstance(total_rate, (int, float, str)):
        total_price = self._extract_number(total_rate)

      # Amenities & Images
      amenities = p.get("amenities", [])
      if not isinstance(amenities, list):
        amenities = []

      images = []
      if p.get("images"):
        for img in p.get("images", []):
          if isinstance(img, dict) and img.get("original_image"):
            images.append(img.get("original_image"))
          elif isinstance(img, dict) and img.get("thumbnail"):
            images.append(img.get("thumbnail"))
          elif isinstance(img, str):
            images.append(img)
      elif p.get("thumbnail"):
        images.append(p.get("thumbnail"))

      # Booking site price sources in search result
      price_sources: List[HotelPriceSource] = []
      raw_prices = p.get("prices", [])
      if isinstance(raw_prices, list):
        for rp in raw_prices:
          s_name = rp.get("source") or rp.get("booking_site") or "Booking Site"
          s_price = self._extract_number(
              rp.get("rate_per_night") or rp.get("price")
          )
          if s_price is not None:
            price_sources.append(
                HotelPriceSource(
                    source_name=s_name,
                    price=s_price,
                    currency=currency,
                    booking_url=rp.get("link"),
                )
            )

      # Mark cheapest booking site if multiple exist
      if price_sources:
        lowest_s_price = min(ps.price for ps in price_sources)
        for ps in price_sources:
          if ps.price == lowest_s_price:
            ps.is_cheapest = True

      # Legitimate provider link only
      booking_url = p.get("link")
      if not booking_url and price_sources:
        booking_url = price_sources[0].booking_url

      free_cancel = (
          "free cancellation" in [a.lower() for a in amenities]
          or p.get("free_cancellation") is True
      )

      hotel_opt = HotelOption(
          id=str(hotel_id),
          provider="serpapi_google_hotels",
          name=name,
          address=p.get("description") or p.get("neighborhood") or "",
          latitude=lat,
          longitude=lon,
          star_class=hotel_class,
          rating=rating,
          review_count=review_count,
          nightly_price=nightly_price,
          total_price=total_price,
          currency=currency,
          check_in_date=check_in_date,
          check_out_date=check_out_date,
          free_cancellation=free_cancel,
          amenities=amenities[:8],
          images=images[:4],
          price_sources=price_sources,
          booking_url=booking_url,
          raw_provider_data={"property_token": p.get("property_token")},
      )
      hotels.append(hotel_opt)

    return hotels

  def parse_property_details(
      self, data: Dict[str, Any], currency: str = "INR"
  ) -> List[HotelPriceSource]:
    """Parses SerpApi Google Hotels property details to extract booking site comparison."""
    prices_list = (
        data.get("prices", [])
        or data.get("featured_prices", [])
        or data.get("booking_options", [])
    )
    sources: List[HotelPriceSource] = []

    for item in prices_list:
      site_name = (
          item.get("source")
          or item.get("vendor")
          or item.get("name")
          or "Partner Site"
      )
      rate_info = (
          item.get("rate_per_night")
          or item.get("price")
          or item.get("total_rate")
      )
      price_val = self._extract_number(rate_info)
      link = item.get("link") or item.get("url")

      if price_val is not None:
        sources.append(
            HotelPriceSource(
                source_name=site_name,
                price=price_val,
                currency=currency,
                booking_url=link,
            )
        )

    if sources:
      lowest_val = min(s.price for s in sources)
      for s in sources:
        if s.price == lowest_val:
          s.is_cheapest = True

    return sources

  async def search_hotels(self, req: HotelSearchRequest) -> List[HotelOption]:
    """Searches hotels for destination and dates via SerpApi Google Hotels.

    Falls back to Geoapify if SerpApi is unavailable or unconfigured,
    clearly labeled as 'No price data available'.
    """
    params = {
        "engine": "google_hotels",
        "q": f"Hotels in {req.destination}",
        "check_in_date": req.check_in_date,
        "check_out_date": req.check_out_date,
        "adults": req.travelers,
        "currency": req.currency,
        "gl": "in",
        "hl": "en",
    }

    if req.min_rating:
      # SerpApi codes: 7 = 3.5+, 8 = 4.0+, 9 = 4.5+ (not the raw number)
      if req.min_rating >= 4.5:
        params["rating"] = 9
      elif req.min_rating >= 4.0:
        params["rating"] = 8
      elif req.min_rating >= 3.5:
        params["rating"] = 7
    if req.star_class:
      params["hotel_class"] = str(req.star_class)
    if req.free_cancellation:
      params["free_cancellation"] = "true"
    if req.min_price:
      params["min_price"] = int(req.min_price)
    if req.max_price:
      params["max_price"] = int(req.max_price)

    try:
      data = await serpapi_client.search(params)
      hotels = self.parse_serpapi_hotels(
          data,
          check_in_date=req.check_in_date,
          check_out_date=req.check_out_date,
          currency=req.currency,
      )

      # Enforce the filters locally too, in case the provider ignores one
      if req.min_rating:
        hotels = [h for h in hotels if h.rating is None or h.rating >= req.min_rating]
      if req.star_class:
        hotels = [h for h in hotels if h.star_class is None or h.star_class >= req.star_class]
      if req.free_cancellation:
        hotels = [h for h in hotels if h.free_cancellation is not False]
      if req.max_price:
        hotels = [h for h in hotels if h.nightly_price is None or h.nightly_price <= req.max_price]

      # Apply recommendation labels
      hotels = (
          hotel_recommendation_service.compute_labels_and_recommendations(
              hotels
          )
      )

      # Apply sorting
      hotels = hotel_recommendation_service.sort_hotels(hotels, req.sort_by)
      return hotels

    except Exception as exc:
      logger.warning(
          f"SerpApi Google Hotels failed for '{req.destination}': {exc}"
      )
      # Check if we should attempt Geoapify unpriced fallback (Section 7A & 30)
      if (
          settings.GEOAPIFY_API_KEY
          and settings.GEOAPIFY_API_KEY != "your_geoapify_api_key_here"
      ):
        logger.info("Falling back to unpriced Geoapify hotel discovery.")
        return await self._geoapify_unpriced_fallback(req)
      raise

  async def get_hotel_property_details(
      self,
      property_token: str,
      check_in_date: str,
      check_out_date: str,
      currency: str = "INR",
      adults: int = 1,
  ) -> List[HotelPriceSource]:
    """Fetches full booking-site price comparison on-demand when user clicks a hotel."""
    params = {
        "engine": "google_hotels",
        "property_token": property_token,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "currency": currency,
        "adults": adults,
        "gl": "in",
        "hl": "en",
    }

    data = await serpapi_client.search(params)
    return self.parse_property_details(data, currency=currency)

  async def _geoapify_unpriced_fallback(
      self, req: HotelSearchRequest
  ) -> List[HotelOption]:
    """Fallback discovering real hotels via Geoapify, explicitly labeled 'No price data available'."""
    from app.services.geocoding_service import geocoding_service
    from app.services.places_service import _fetch_geoapify_places, _geoapify_feature_to_dict

    try:
      center = geocoding_service.resolve_center(location=req.destination)
      features = _fetch_geoapify_places(
          center.latitude,
          center.longitude,
          radius_m=8000,
          categories=["accommodation.hotel"],
          limit=15,
      )
      hotels: List[HotelOption] = []
      for f in features:
        p = _geoapify_feature_to_dict(f)
        if not p.get("name") or p["name"].lower() in (
            "hotel",
            "unnamed",
            "unknown",
        ):
          continue
        hotels.append(
            HotelOption(
                id=f"htl_geo_{p.get('id', '')}",
                provider="geoapify_fallback",
                name=p["name"],
                address=p.get("address") or "",
                latitude=p.get("latitude"),
                longitude=p.get("longitude"),
                rating=p.get("rating"),
                review_count=p.get("rating_count"),
                nightly_price=None,
                total_price=None,
                currency=req.currency,
                check_in_date=req.check_in_date,
                check_out_date=req.check_out_date,
                amenities=[],
                price_status="unpriced_fallback",
                recommendation_labels=["No price data available"],
                recommendation_reason=(
                    "Discovered via Geoapify without live SerpApi pricing"
                ),
            )
        )
      return hotels
    except Exception as exc:
      logger.warning(f"Geoapify hotel fallback also failed: {exc}")
      return []


hotel_service = HotelService()
