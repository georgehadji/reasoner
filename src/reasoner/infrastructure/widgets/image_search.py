"""
Image Search Widget

Searches for images using multi-backend search.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetResult, WidgetType


class ImageSearchWidget(BaseWidget):
    """
    Image search widget using multi-backend search.
    
    Features:
    - Visual search results
    - Thumbnail previews
    - Multiple image sources
    """
    
    name = "image_search"
    widget_type = WidgetType.IMAGE_SEARCH
    description = "Visual image search results"
    
    trigger_patterns = [
        re.compile(r'(?:show|find|search)\s+images\s+(?:for)?\s*(.+)', re.I),
        re.compile(r'(?:images|pictures|photos)\s+(?:of|for)?\s*(.+)', re.I),
        re.compile(r'show\s+me\s+(?:some)?\s*(?:images|pictures|photos)\s+(?:of)?\s*(.+)', re.I),
    ]
    
    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """Extract search query from match."""
        search_query = None
        
        if match.lastindex and match.lastindex >= 1:
            search_query = match.group(1).strip()
        else:
            # Clean up query
            search_query = re.sub(
                r'^(show|find|search|images|pictures|photos|show me)\s+(images|pictures|photos|for|of|some)?\s*',
                '',
                query,
                flags=re.I
            ).strip()
        
        return {'query': search_query, 'limit': 20}
    
    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search for images."""
        query = params.get('query', '')
        limit = params.get('limit', 20)
        
        if not query:
            return {'error': 'Search query not specified'}
        
        results = await self._search_images(query, limit)
        
        return {
            'query': query,
            'results': results,
            'total': len(results),
        }
    
    async def _search_images(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search images using SearXNG via the shared URL helper."""
        import httpx
        import reasoner.infrastructure.search.discovery as _disc
        urls = _disc.get_searxng_urls()
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        url,
                        params={"q": query, "format": "json", "categories": "images"},
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        return [
                            {
                                'title': r.get('title', ''),
                                'url': r.get('url', ''),
                                'img_src': r.get('img_src', r.get('url', '')),
                                'thumbnail': r.get('thumbnail', ''),
                                'source': r.get('source', ''),
                            }
                            for r in results[:limit]
                        ]
            except Exception:
                continue
        return []
