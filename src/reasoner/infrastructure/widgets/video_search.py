"""
Video Search Widget

Searches for videos using multi-backend search.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetResult, WidgetType


class VideoSearchWidget(BaseWidget):
    """
    Video search widget using multi-backend search.
    
    Features:
    - Video search results
    - Thumbnail previews
    - Duration information
    - Multiple video sources (YouTube, Vimeo, etc.)
    """
    
    name = "video_search"
    widget_type = WidgetType.VIDEO_SEARCH
    description = "Video content search results"
    
    trigger_patterns = [
        re.compile(r'(?:show|find|search)\s+videos?\s+(?:for)?\s*(.+)', re.I),
        re.compile(r'(?:videos?|youtube)\s+(?:of|for|about)?\s*(.+)', re.I),
        re.compile(r'show\s+me\s+(?:some)?\s*videos?\s+(?:of)?\s*(.+)', re.I),
        re.compile(r'(?:watch|view)\s+(?:a)?\s*video\s+(?:about|on|for)?\s*(.+)', re.I),
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
                r'^(show|find|search|videos?|youtube|show me|watch|view)\s+(videos?|for|of|about|on|for|a)?\s*',
                '',
                query,
                flags=re.I
            ).strip()
        
        return {'query': search_query, 'limit': 20}
    
    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search for videos."""
        query = params.get('query', '')
        limit = params.get('limit', 20)
        
        if not query:
            return {'error': 'Search query not specified'}
        
        results = await self._search_videos(query, limit)
        
        return {
            'query': query,
            'results': results,
            'total': len(results),
        }
    
    async def _search_videos(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Search videos using SearXNG via the shared URL helper."""
        import httpx
        import reasoner.infrastructure.search.discovery as _disc
        urls = _disc.get_searxng_urls()
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        url,
                        params={"q": query, "format": "json", "categories": "videos"},
                    )
                    if resp.status_code == 200:
                        results = resp.json().get("results", [])
                        return [
                            {
                                'title': r.get('title', ''),
                                'url': r.get('url', ''),
                                'thumbnail': r.get('thumbnail', ''),
                                'source': r.get('source', ''),
                                'duration': r.get('duration', ''),
                                'published': r.get('publishedDate', r.get('published_date', '')),
                            }
                            for r in results[:limit]
                        ]
            except Exception:
                continue
        return []
