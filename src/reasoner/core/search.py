"""
Reasoner - Web Discovery Tool
Provides internal web search capabilities for context enrichment.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from typing import Any, Optional, Literal, Protocol

import httpx

from reasoner.core.temperatures import NON_PHASE_TEMPERATURES
from reasoner.core.settings import settings
from reasoner.core.rerank import rerank_documents
from reasoner.core.constants import (
    TIMEOUTS,
    DEFAULT_MAX_DECOMPOSED_QUERIES,
    DEFAULT_SEARCH_RESULTS,
    TRUNCATION,
    MODEL_GEMINI_FLASH,
    MODEL_QWEN35_9B,
    MODEL_QWEN35_FLASH,
)

# ── Dependency Injection for core → infrastructure boundary ───────
# These are set by api/__init__.py during bootstrap, inverting the
# dependency: core defines the port, infrastructure provides the impl.
# Thread-safe via single assignment (not atomic, but set once at startup).
import threading

_BUILD_PROVIDER = None

def set_build_provider(fn):
    """Inject provider builder function (called from api/__init__.py)."""
    global _BUILD_PROVIDER
    _BUILD_PROVIDER = fn

def _get_build_provider():
    global _BUILD_PROVIDER
    return _BUILD_PROVIDER

# Re-export search client helpers so tests can import them from core.search.
# Lazy to avoid circular imports at module load time.
_DISCOVERY_MODULE = None


def _get_discovery_module():
    global _DISCOVERY_MODULE
    if _DISCOVERY_MODULE is None:
        _DISCOVERY_MODULE = importlib.import_module(
            "reasoner.infrastructure.search.discovery"
        )
    return _DISCOVERY_MODULE


logger = logging.getLogger(__name__)

SourceType = Literal["general", "academic", "social", "news", "code"]


# File extensions and URL patterns that are unlikely to yield readable article content
_REJECTED_EXTENSIONS = frozenset([".json", ".xml", ".csv", ".zip", ".pdf"])
_RAW_BLOB_RE = re.compile(r"/blob/[^/]+/.*\.(json|xml|csv|zip|pdf)", re.IGNORECASE)


# Known off-topic domains/patterns for high-collision acronyms and low-signal sources
_OFF_TOPIC_PATTERNS = [
    ("nerdwallet.com", None),  # tax AGI
    ("wikipedia.org", "one big beautiful bill act"),
    ("huggingface.co", "vocab.txt"),
    ("huggingface.co", "tokenizer.json"),
    ("llm-guide.com", None),  # legal-degree LLM, not AI
    ("pluralsight.com", "best ai models"),  # generic roundup
    ("wordreference.com", None),  # dictionary definitions
    ("facebook.com", None),  # social noise
    ("biography.com", None),  # celebrity bios
    ("imdb.com", None),  # movie/TV data
    ("thetimes.com", None),  # paywalled general news
    ("reddit.com", None),  # often noisy / unsourced
    ("twitter.com", None),  # social noise
    ("x.com", None),  # social noise
    ("pinterest.com", None),  # image SEO spam
    ("quora.com", None),  # opinion-heavy, low sourcing
    ("yahoo.com", None),  # generic aggregator
    ("slideshare.net", None),  # slide decks with thin content
    ("steamcommunity.com", None),  # UGC + adult phrases surfaced in prior runs
    ("that80sdude.com", None),  # pop-culture listicles
]

# Low-signal title patterns (listicles, generic roundups, clickbait, filler guides)
_LOW_SIGNAL_TITLE_RE = re.compile(
    r"(\b("
    r"top\s+(\d+\s+)?(programs|schools|universities|courses|colleges)|"
    r"top\s+\d+|best\s+\d+|\d+\s+best|\d+\s+ways?|\d+\s+ideas?|"
    r"discover\s+\d+|\d+\s+things?|\d+\s+tips?|\d+\s+reasons?|"
    r"ultimate\s+(guide|list)|beginners?\s+guide|(complete|definitive)\s+(guide|list)|"
    r"guide\s+to\s+\w+|cheat\s+sheet|crash\s+course|\w+\s+101|"
    r"everything\s+you\s+need|all\s+you\s+need\s+to\s+know|"
    r"\d{4}\s+(guide|list|roundup)|what\s+is\s+\w+\s+and\s+how"
    r")\b)",
    re.IGNORECASE,
)

# Common English stop words to exclude from keyword extraction
_STOP_WORDS = frozenset([
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
    "because", "until", "while", "what", "which", "who", "whom", "this",
    "that", "these", "those", "i", "me", "my", "myself", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "s", "t", "don", "doesn", "didn", "wasn", "weren",
    "won", "wouldn", "couldn", "shouldn", "isn", "aren", "hasn", "haven",
    "hadn", "ain", "ma", "mightn", "mustn", "needn", "shan", "shouldn",
    "wasn", "weren", "won", "wouldn",
])

# Regex to extract English keywords from mixed-language text
_KEYWORD_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}", re.IGNORECASE)

# Minimum useful snippet length — anything shorter is likely a failed extraction
_MIN_SNIPPET_LEN = 50


# ─────────────────────────────────────────────
#  URL Normalization
# ─────────────────────────────────────────────

def _normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication. 
    Handles protocol, www, trailing slashes (even before query params), and fragments.
    """
    if not url:
        return ""
    try:
        p = urlparse(url.lower())
        # Remove www. from netloc
        netloc = p.netloc[4:] if p.netloc.startswith("www.") else p.netloc
        # Clean path: remove trailing slash
        path = p.path.rstrip("/")
        # Reconstruct without scheme and fragment
        # Using a simple string concat to avoid urlunparse adding back scheme://
        return f"{netloc}{path}{'?' + p.query if p.query else ''}"
    except Exception:
        # Fallback to a simpler version if parsing fails
        u = url.lower().split("://")[-1].split("#")[0].rstrip("/")
        return u[4:] if u.startswith("www.") else u


# ─────────────────────────────────────────────
#  BM25 Re-ranking
# ─────────────────────────────────────────────

def _bm25_score(query: str, result: dict, k1: float = 1.5, b: float = 0.75) -> float:
    """
    Simplified BM25-style relevance score between a query and a search result.

    No corpus-level IDF is computed — term weighting is uniform across query tokens.
    Title matches are weighted 3× vs content matches to surface on-topic titles.

    Returns a non-negative float; higher = more relevant.
    """
    query_tokens = {
        t for t in _KEYWORD_RE.findall(query.lower())
        if t not in _STOP_WORDS and len(t) > 2
    }
    if not query_tokens:
        return 0.0

    title_tokens = _KEYWORD_RE.findall((result.get("title") or "").lower())
    content_tokens = _KEYWORD_RE.findall((result.get("content") or "").lower())

    # Expected average lengths (heuristic, not corpus-derived)
    _AVG_TITLE = 10
    _AVG_CONTENT = 80

    from collections import Counter
    title_counts = Counter(title_tokens)
    content_counts = Counter(content_tokens)
    score = 0.0
    for term in query_tokens:
        tf_t = title_counts.get(term, 0)
        if tf_t:
            denom = tf_t + k1 * (1.0 - b + b * max(len(title_tokens), 1) / _AVG_TITLE)
            score += 3.0 * tf_t * (k1 + 1) / denom

        tf_c = content_counts.get(term, 0)
        if tf_c:
            denom = tf_c + k1 * (1.0 - b + b * max(len(content_tokens), 1) / _AVG_CONTENT)
            score += tf_c * (k1 + 1) / denom

    return score / len(query_tokens)


# ─────────────────────────────────────────────
#  Freshness Scoring
# ─────────────────────────────────────────────

def _parse_freshness(result: dict) -> float:
    """
    Derive a freshness score in [0, 1] from a result's publishedDate field.

    Returns 0.5 (neutral) when no date is available so non-dated results
    are not unfairly penalised against fresh content.

    Score curve: 1.0 for today → ~0.5 at 1 year → asymptotes toward 0.
    """
    raw = result.get("publishedDate") or result.get("published_date") or ""
    if not raw:
        return 0.5
    try:
        pub = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        days_old = max(0, (datetime.now(timezone.utc) - pub).days)
        return 1.0 / (1.0 + days_old / 365.0)
    except Exception:
        return 0.5


# ─────────────────────────────────────────────
#  Quality Filter
# ─────────────────────────────────────────────

def _should_include_result(result: dict[str, Any]) -> bool:
    """
    Gatekeeper for search results.
    Rejects raw data files, code blobs, off-topic domains, and snippets that are too short to be useful.
    """
    url = result.get("url", "")
    if not url:
        return False

    parsed = urlparse(url)
    path = parsed.path.lower()
    title = (result.get("title") or "").lower()

    # Reject known non-article file extensions
    if any(path.endswith(ext) for ext in _REJECTED_EXTENSIONS):
        return False

    # Reject GitHub / GitLab raw blob URLs for data files
    if _RAW_BLOB_RE.search(path):
        return False

    # Reject very short snippets (likely failed extraction or useless landing pages)
    content = (result.get("content") or "").strip()
    if len(content) < _MIN_SNIPPET_LEN:
        return False

    # Reject low-signal listicles and generic roundups
    if _LOW_SIGNAL_TITLE_RE.search(title):
        return False

    # Reject obvious adult/NSFW content by keyword
    lowered_all = f"{url.lower()} {title}".lower()
    if any(bad in lowered_all for bad in ("gloryhole", "porn", "nsfw", "xxx")):
        return False

    # Reject known off-topic domain / pattern combinations
    netloc = parsed.netloc.lower()
    for domain_pat, title_pat in _OFF_TOPIC_PATTERNS:
        if domain_pat in netloc:
            if title_pat is None or title_pat in title:
                return False

    return True


# ─────────────────────────────────────────────
#  Discovery Client
# ─────────────────────────────────────────────

from reasoner.core.ports.search_port import SearchServicePort

_DISCOVERY_EXPORTS = {
    "PerplexitySearchClient",
    "get_search_client",
    "_decompose_query",
    "_extract_search_keywords",
    "_DECOMPOSITION_CACHE",
    "_DECOMPOSITION_TTL_SECONDS",
}


def __getattr__(name: str):
    if name in _DISCOVERY_EXPORTS:
        value = getattr(_get_discovery_module(), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


