"""
Discover Widget

Provides trending content aggregation by topic.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetType


class DiscoverWidget(BaseWidget):
    """
    Discover widget for trending content.
    
    Features:
    - Topic-based aggregation (tech, finance, science, sports, entertainment)
    - Multiple source integration
    - Real-time trending content
    """

    name = "discover"
    widget_type = WidgetType.DISCOVER
    description = "Trending content aggregation by topic"

    trigger_patterns = [
        re.compile(r'(?:trending|discover|latest news)\s+(?:in|about)?\s*([a-z]+)?', re.I),
        re.compile(r'(?:show|get|find)\s+(?:the )?(?:latest )?news\s+(?:in|about)?\s*([a-z]+)?', re.I),
        re.compile(r"^what'?s?\s+(?:the )?latest\s+(?:in|for)?\s*([a-z]+)", re.I),
        re.compile(r'(?:tech|finance|science|sports|entertainment)\s+news', re.I),
    ]

    topics = {
        'tech': {
            'queries': ['technology news', 'latest tech', 'AI', 'science and innovation'],
            'sites': ['techcrunch.com', 'wired.com', 'theverge.com', 'arstechnica.com'],
        },
        'finance': {
            'queries': ['finance news', 'economy', 'stock market', 'investing'],
            'sites': ['bloomberg.com', 'cnbc.com', 'marketwatch.com', 'reuters.com'],
        },
        'science': {
            'queries': ['science news', 'research', 'discovery', 'space'],
            'sites': ['nature.com', 'science.org', 'scientificamerican.com', 'space.com'],
        },
        'sports': {
            'queries': ['sports news', 'latest sports'],
            'sites': ['espn.com', 'bbc.com/sport', 'skysports.com'],
        },
        'entertainment': {
            'queries': ['entertainment news', 'movies', 'TV shows'],
            'sites': ['hollywoodreporter.com', 'variety.com', 'deadline.com'],
        },
    }

    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """Extract topic from match."""
        topic = 'tech'  # Default

        # Check for explicit topic in query
        query_lower = query.lower()
        for t in self.topics.keys():
            if t in query_lower:
                topic = t
                break

        # Check capture group
        if match.lastindex and match.lastindex >= 1:
            captured = match.group(1)
            if captured and captured.lower() in self.topics:
                topic = captured.lower()

        return {'topic': topic}

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch trending content for topic."""
        topic = params.get('topic', 'tech')

        if topic not in self.topics:
            topic = 'tech'

        topic_config = self.topics[topic]
        results = []
        seen_urls = set()

        # Search using multi-backend client
        for query in topic_config['queries']:
            search_results = await self._search_web(query)

            for result in search_results[:5]:
                url = result.get('url', '')
                if url not in seen_urls:
                    seen_urls.add(url)
                    results.append({
                        'title': result.get('title', ''),
                        'url': url,
                        'content': result.get('content', ''),
                        'source': result.get('source', ''),
                        'published': result.get('publishedDate', ''),
                    })

            if len(results) >= 10:
                break

        if not results:
            # Return demo content if no results
            results = [
                {
                    'title': f'Latest {topic} news - Demo Mode',
                    'url': f"https://{topic_config['sites'][0]}",
                    'content': f'Configure search API keys for live {topic} content',
                    'source': topic_config['sites'][0],
                    'published': '',
                },
            ]

        return {
            'topic': topic,
            'results': results[:10],
            'total': len(results),
            'sources': topic_config['sites'],
        }

    async def _search_web(self, query: str) -> list[dict[str, Any]]:
        """Search using multi-backend search client."""
        from reasoner.infrastructure.search.discovery import get_search_client
        try:
            client, _ = await get_search_client()
            return await client.search(query, num_results=5)
        except Exception:
            return []
