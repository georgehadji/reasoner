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
        """Search images using multi-backend search client."""
        from reasoner.infrastructure.search.discovery import get_search_client
        
        try:
            client, _ = await get_search_client()
            results = await client.search(query, num_results=limit)
            return [
                {
                    'title': r.get('title', ''),
                    'url': r.get('url', ''),
                    'img_src': r.get('img_src', r.get('url', '')),
                    'thumbnail': r.get('thumbnail', ''),
                    'source': r.get('source', ''),
                }
                for r in results
            ]
        except Exception:
            return []
