"""Search service adapter (Section 26).
Future interface for DuckDuckGo/Brave/Serper web queries.
"""

from typing import List, Dict, Any


class SearchService:
    async def query(self, query_text: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Mock web search provider interface."""
        return [
            {
                "title": f"Local Discovery Guide for {query_text}",
                "snippet": "Curated local recommendations and historical points of interest.",
                "url": "https://example.com/guide",
                "source": "mock-search"
            }
        ]


search_service = SearchService()
