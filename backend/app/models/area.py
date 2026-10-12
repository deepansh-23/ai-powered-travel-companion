"""Pydantic models for Area Guide / Summarizer (Section 10 & Section 23).
"""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


class AreaSummarizeRequest(BaseModel):
    area: str = Field(..., min_length=2, description="Target area or neighborhood")
    radius_km: float = Field(3.0, ge=0.5, le=30.0)


class AreaSection(BaseModel):
    title: str
    summary: str
    highlights: List[str] = Field(default_factory=list)


class QuickFacts(BaseModel):
    walkability: str
    transit_connectivity: str
    vibe: str
    best_for: str
    average_meal_cost: str


class AreaSummarizeResponse(BaseModel):
    area_name: str
    region: str
    character_summary: str
    quick_facts: QuickFacts
    sections: Dict[str, AreaSection]
    advantages: List[str]
    limitations: List[str]
    suitability: List[str]
    source: str
    data_mode: Literal["mock", "live"]
