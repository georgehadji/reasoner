"""
Smart Suggestions Engine
Generates intelligent search suggestions based on partial queries.
"""

from __future__ import annotations

import logging
from typing import Any
from dataclasses import dataclass

from reasoner.core.constants import DEFAULT_NUM_SUGGESTIONS
from reasoner.core.search import SourceType

logger = logging.getLogger(__name__)


@dataclass
class SuggestionRequest:
    """Request for generating suggestions."""
    query: str
    chat_history: list[list[str]] | None = None
    max_suggestions: int = DEFAULT_NUM_SUGGESTIONS


@dataclass
class SuggestionResponse:
    """Response with generated suggestions."""
    suggestions: list[str]
    query: str


# Topic-based suggestion templates
SUGGESTION_TEMPLATES = {
    "tech": [
        "latest developments in {topic}",
        "breakthrough in {topic} 2026",
        "how does {topic} work",
        "{topic} vs alternatives",
        "future of {topic}",
    ],
    "science": [
        "recent discoveries in {topic}",
        "{topic} research papers",
        "explain {topic} simply",
        "{topic} applications",
        "{topic} scientific consensus",
    ],
    "programming": [
        "{topic} best practices",
        "{topic} tutorial for beginners",
        "{topic} common mistakes",
        "{topic} vs other solutions",
        "{topic} code examples",
    ],
    "general": [
        "what is {topic}",
        "history of {topic}",
        "{topic} benefits and drawbacks",
        "how to learn {topic}",
        "{topic} real-world examples",
    ],
}


def detect_topic(query: str) -> str:
    """Detect the topic category from the query."""
    query_lower = query.lower()
    
    tech_keywords = ["ai", "machine learning", "python", "javascript", "api", "software", "code", "programming", "llm", "model"]
    science_keywords = ["physics", "biology", "chemistry", "research", "study", "experiment", "scientific"]
    programming_keywords = ["code", "function", "variable", "loop", "array", "debug", "error", "syntax"]
    
    if any(keyword in query_lower for keyword in programming_keywords):
        return "programming"
    elif any(keyword in query_lower for keyword in tech_keywords):
        return "tech"
    elif any(keyword in query_lower for keyword in science_keywords):
        return "science"
    else:
        return "general"


def extract_topic(query: str) -> str:
    """Extract the main topic from the query."""
    # Remove common question words
    question_words = ["what", "how", "why", "when", "where", "who", "which", "is", "are", "does", "do", "can", "could", "would", "should"]
    words = query.lower().split()
    topic_words = [w for w in words if w not in question_words and len(w) > 2]
    
    if topic_words:
        return " ".join(topic_words[:3])  # Return first 3 meaningful words
    return query


def generate_suggestions(request: SuggestionRequest) -> SuggestionResponse:
    """
    Generate intelligent search suggestions based on the query.
    
    Uses a combination of:
    - Topic detection
    - Template-based suggestions
    - Query completion patterns
    """
    query = request.query.strip()
    
    if not query:
        return SuggestionResponse(suggestions=[], query=query)
    
    topic_category = detect_topic(query)
    topic = extract_topic(query)
    
    suggestions = []
    
    # Generate suggestions from templates
    templates = SUGGESTION_TEMPLATES.get(topic_category, SUGGESTION_TEMPLATES["general"])
    for template in templates[:request.max_suggestions]:
        suggestion = template.replace("{topic}", topic)
        if suggestion.lower() != query.lower():
            suggestions.append(suggestion)
    
    # Add query completion patterns
    if len(query.split()) < 4:
        completion_patterns = [
            f"{query} explained",
            f"{query} examples",
            f"{query} guide",
        ]
        for pattern in completion_patterns:
            if pattern not in suggestions and len(suggestions) < request.max_suggestions:
                suggestions.append(pattern)
    
    # Limit to max_suggestions
    suggestions = suggestions[:request.max_suggestions]
    
    logger.info(f"Generated {len(suggestions)} suggestions for query: {query[:50]}...")
    
    return SuggestionResponse(suggestions=suggestions, query=query)


async def generate_suggestions_async(request: SuggestionRequest) -> SuggestionResponse:
    """Async wrapper for generate_suggestions."""
    return generate_suggestions(request)
