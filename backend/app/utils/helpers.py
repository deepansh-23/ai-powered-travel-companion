"""General helper utilities for IDs, logging privacy, and description synthesis.
"""

import uuid
import re
from typing import Optional


def generate_id(prefix: str = "item") -> str:
    """Generate a clean URL-friendly unique identifier."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def mask_coordinates_for_logs(lat: Optional[float], lon: Optional[float]) -> str:
    """Round coordinates to 2 decimal places (~1.1 km precision) to protect user privacy in logs."""
    if lat is None or lon is None:
        return "none"
    try:
        return f"{round(float(lat), 2)},{round(float(lon), 2)}"
    except Exception:
        return "invalid"


def synthesize_fallback_description(name: str, category: str, address: Optional[str] = None) -> str:
    """Create a factual 2-sentence description grounded only in known data (Section 50.7).
    Never invents unverified claims regarding hours, ratings, or prices.
    """
    clean_cat = category.replace("_", " ").title()
    desc = f"{name} is a local {clean_cat.lower()}"
    if address:
        desc += f" located at {address}."
    else:
        desc += " situated in the local area."
    desc += f" It provides standard {clean_cat.lower()} services for local residents and visitors."
    return desc
