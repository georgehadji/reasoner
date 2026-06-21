"""
Image Search Widget

Searches for images using SearXNG.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetResult, WidgetType


class ImageSearchWidget(BaseWidget):
    """
    Image search widget using SearXNG.
    
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
        """Search images using SearXNG."""
        import httpx
        from reasoner.infrastructure.search.discovery import get_searxng_urls
        
        searxng_urls = get_searxng_urls()
        
        for url in searxng_urls:
            from reasoner.core.constants import TIMEOUTS
            try:
                async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET_SHORT) as client:
                    response = await client.get(
                        url,
                        params={
                            'q': query,
                            'format': 'json',
                            'categories': 'images',
                        },
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        
                        for result in data.get('results', [])[:limit]:
                            results.append({
                                'title': result.get('title', ''),
                                'url': result.get('url', ''),
                                'img_src': result.get('img_src', ''),
                                'thumbnail': result.get('thumbnail', ''),
                                'source': result.get('source', ''),
                                'width': result.get('width'),
                                'height': result.get('height'),
                            })
                        
                        return results
                        
            except Exception:
                continue
        
        return []
