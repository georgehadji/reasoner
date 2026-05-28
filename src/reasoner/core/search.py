"""
Reasoner - Web Discovery Tool
Provides internal web search capabilities for context enrichment.
"""

from __future__ import annotations

import asyncio
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
    DEFAULT_SEARXNG_URL,
    TIMEOUTS,
    DEFAULT_MAX_DECOMPOSED_QUERIES,
    DEFAULT_SEARCH_RESULTS,
    TRUNCATION,
    MODEL_GEMINI_FLASH,
    MODEL_QWEN35_9B,
    MODEL_QWEN35_FLASH,
)

# Deferred import to avoid circular dependencies at module load time
_build_provider = None

def _get_build_provider():
    global _build_provider
    if _build_provider is None:
        from reasoner.infrastructure.llm.registry import build_provider
        _build_provider = build_provider
    return _build_provider

logger = logging.getLogger(__name__)

# Circuit breaker for SearXNG — prevents 30s hangs when instance is down
from reasoner.circuit_breaker import get_circuit_breaker

_SEARXNG_CB = get_circuit_breaker("searxng")
_SEARXNG_CB.config.failure_threshold = 3
_SEARXNG_CB.config.success_threshold = 2
_SEARXNG_CB.config.timeout_seconds = 30.0

# Source type categories for specialized searches
SOURCE_TYPE_ENGINES: dict[str, list[str]] = {
    "general": [],  # Use default engines
    "academic": ["arxiv", "google_scholar", "crossref", "semantic_scholar", "pubmed"],
    "social": ["reddit", "twitter", "hackernews", "mastodon", "wikipedia"],
    "news": ["google_news", "bing_news", "newsapi", "ddg_news"],
    "code": ["github", "gitlab", "stackoverflow", "npm"],
}

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
    Derive a freshness score in [0, 1] from SearXNG's publishedDate field.

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

from reasoner.infrastructure.search.port import SearchServicePort
from reasoner.infrastructure.search.searxng_adapter import SearXNGAdapter

# DiscoveryClient now wraps SearXNGAdapter to conform to SearchServicePort
class DiscoveryClient(SearchServicePort):
    def __init__(self, base_url: str = DEFAULT_SEARXNG_URL):
        self.adapter = SearXNGAdapter(base_url=base_url)

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return await self.adapter.search(
            query, num_results, categories, source_type, domain
        )

    async def close(self) -> None:
        await self.adapter.close()


# ─────────────────────────────────────────────
#  Perplexity Search Client (Strategy Pattern)
# ─────────────────────────────────────────────

class PerplexitySearchClient:
    """Search client using Perplexity Sonar via OpenRouter.

    Returns synthesized results with citations.
    Falls back to empty list on any error.
    """

    def __init__(self, model_id: str = "sonar") -> None:
        build_provider = _get_build_provider()
        self.provider = build_provider(model_id)

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        try:
            kwargs: dict[str, Any] = {
                "model": self.provider.model,
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 2048,
            }
            if getattr(self.provider, "extra_body", None):
                kwargs["extra_body"] = self.provider.extra_body

            response = await self.provider.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            citations = getattr(response, "citations", [])

            url = (citations[0] or "") if citations else ""
            if not url:
                # Perplexity via OpenRouter often returns empty citations.
                # Use a synthetic URL so the result isn't dropped by downstream filters.
                url = f"perplexity://synthetic/{query[:40].replace(' ', '_')}"
            return [{
                "title": f"Perplexity result for: {query[:50]}",
                "url": url,
                "content": content,
                "snippet": content[:TRUNCATION.SNIPPET],
                "source": "perplexity",
                "source_type": "synthetic",
                "citations": citations,
                "freshness_score": 1.0,
            }]
        except Exception as e:
            logger.error("Perplexity search via OpenRouter failed: %s", e)
            return []

    async def close(self):
        pass


class SearchClient(Protocol):
    """Protocol for search clients (Strategy Pattern)."""

    async def search(
        self,
        query: str,
        num_results: int = DEFAULT_SEARCH_RESULTS,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]: ...

    async def close(self): ...


_default_client: Optional[DiscoveryClient] = None


def reset_discovery_client() -> None:
    """Reset the global discovery client. Call this if base_url changes."""
    global _default_client
    old = _default_client
    _default_client = None
    if old is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(old.close())
        except RuntimeError:
            try:
                asyncio.run(old.close())
            except Exception:
                pass


# ─────────────────────────────────────────────
#  Query Decomposition
# ─────────────────────────────────────────────

_DECOMPOSITION_MODELS = [MODEL_QWEN35_9B, MODEL_QWEN35_FLASH, MODEL_GEMINI_FLASH]

_DECOMPOSITION_CACHE: dict[str, tuple[list[str], float]] = {}
_DECOMPOSITION_TTL_SECONDS = 300.0
_MAX_DECOMPOSITION_CACHE_SIZE = 512


def _prune_decomposition_cache() -> None:
    excess = len(_DECOMPOSITION_CACHE) - _MAX_DECOMPOSITION_CACHE_SIZE
    if excess > 0:
        sorted_items = sorted(_DECOMPOSITION_CACHE.items(), key=lambda item: item[1][1])
        for key, _ in sorted_items[:excess]:
            del _DECOMPOSITION_CACHE[key]


def _extract_search_keywords(text: str, max_keywords: int = 8) -> str:
    """
    Extract English keywords from mixed-language prompts using regex.
    Returns a space-separated keyword string suitable for search.
    """
    words = _KEYWORD_RE.findall(text)
    cleaned = []
    for w in words:
        w = w.lower().strip("-")
        if len(w) > 2 and w not in _STOP_WORDS:
            cleaned.append(w)
    seen: set[str] = set()
    unique = [w for w in cleaned if not (w in seen or seen.add(w))]
    return " ".join(unique[:max_keywords])


async def _decompose_query(query: str, model_id: str | None = None) -> list[str]:
    """Use a lightweight LLM to break a query into 2-3 focused sub-queries."""
    now = time.monotonic()
    cached = _DECOMPOSITION_CACHE.get(query)
    if cached is not None:
        sub_queries, ts = cached
        if now - ts < _DECOMPOSITION_TTL_SECONDS:
            logger.debug("Decomposition cache hit for query: %r", query[:80])
            return sub_queries
        _DECOMPOSITION_CACHE.pop(query, None)

    system_prompt = (
        "You are a search assistant. Given a user query, break it into 2-3 focused, "
        "standalone search queries that together cover the user's intent. "
        "Output ONLY a JSON array of strings. Do not include markdown, explanations, "
        "or code blocks.\n"
        'Example: ["query 1", "query 2"]'
    )
    build_provider = _get_build_provider()
    provider = build_provider(model_id or _DECOMPOSITION_MODELS[0])
    raw = await provider.complete_with_retry(
        system_prompt=system_prompt,
        user_prompt=query,
        max_tokens=TRUNCATION.SNIPPET,
        temperature=NON_PHASE_TEMPERATURES["search_query_generation"],
    )
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[-1].strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Decomposition JSON parse failed for query: %s", query)
        arr = []
    if not isinstance(arr, list):
        raise ValueError("LLM did not return a JSON array")
    result = [str(item).strip() for item in arr if str(item).strip()]
    result = result[:DEFAULT_MAX_DECOMPOSED_QUERIES]

    _DECOMPOSITION_CACHE[query] = (result, now)
    _prune_decomposition_cache()
    return result


# ─────────────────────────────────────────────
#  Smart Search (with BM25 re-ranking)
# ─────────────────────────────────────────────

async def smart_search(
    query: str,
    source_type: Optional[SourceType] = None,
    num_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Decompose the query via a cheap LLM, run parallel searches,
    deduplicate by normalised URL, BM25-rank by relevance + freshness,
    and return the top N results.

    Falls back to a single keyword-extracted search on decomposition failure.
    """
    client, _ = await get_search_client(source_type=source_type)

    sub_queries: list[str] = []
    last_error: Exception | None = None
    for model_id in _DECOMPOSITION_MODELS:
        try:
            sub_queries = await _decompose_query(query, model_id=model_id)
            if sub_queries:
                break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Smart search decomposition with %s failed (%s). Trying fallback LLM. Raw query: %r",
                model_id, exc, query,
            )

    if not sub_queries:
        logger.warning(
            "Smart search decomposition failed for all LLMs (last error: %s). "
            "Raw query: %r. Falling back to keyword extraction + direct search.",
            last_error, query,
        )
        keyword_query = _extract_search_keywords(query)
        fallback_query = keyword_query if keyword_query else query
        results = await client.search(fallback_query, num_results=num_results, source_type=source_type)
        results.sort(key=lambda r: _bm25_score(query, r), reverse=True)
        return results

    per_query = max(3, num_results // len(sub_queries))

    async def _search_one(q: str) -> tuple[str, list[dict[str, Any]]]:
        results = await client.search(q, num_results=per_query, source_type=source_type)
        return q, results

    tasks = [_search_one(q) for q in sub_queries]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    seen_norms: set[str] = set()
    grouped_results: list[dict[str, Any]] = []

    for item in gathered:
        if isinstance(item, Exception):
            logger.warning("Smart search sub-query failed: %s", item)
            continue
        q, results = item
        for r in results:
            norm = _normalize_url(r.get("url", ""))
            if not norm or norm in seen_norms:
                continue
            seen_norms.add(norm)
            grouped_results.append({**r, "group": q})

    if not grouped_results:
        keyword_query = _extract_search_keywords(query)
        fallback_query = keyword_query if keyword_query else query
        results = await client.search(fallback_query, num_results=num_results, source_type=source_type)
        results.sort(key=lambda r: _bm25_score(query, r), reverse=True)
        return results

    # Re-rank by composite BM25 relevance + freshness before returning
    def _composite_score(r: dict) -> float:
        bm25 = _bm25_score(query, r)
        freshness = r.get("freshness_score", 0.5)
        return bm25 * 0.8 + freshness * 0.2

    grouped_results.sort(key=_composite_score, reverse=True)
    top_candidates = grouped_results[:num_results * 2]

    # Optional: cross-encoder rerank for higher precision
    if settings.COHERE_RERANK_ENABLED and len(top_candidates) > 1:
        try:
            reranked = await rerank_documents(query, top_candidates, top_n=num_results)
            if len(reranked) >= num_results:
                return reranked[:num_results]
        except Exception as exc:
            logger.warning("Rerank step failed in smart_search: %s", exc)

    return top_candidates[:num_results]


# ─────────────────────────────────────────────
#  Utilities
# ─────────────────────────────────────────────

def get_searxng_urls() -> list[str]:
    """Return the list of SearXNG URLs to try, respecting SEARXNG_URL env var."""
    base = os.environ.get("SEARXNG_URL", DEFAULT_SEARXNG_URL).rstrip("/")
    urls = [f"{base}/search"]
    # Always include fallback to 127.0.0.1:8888 (default SearXNG port)
    # If base already uses localhost, also include IP version
    if "localhost" in base:
        ip_base = base.replace("localhost", "127.0.0.1")
        urls.append(f"{ip_base}/search")
    else:
        # Include default IP fallback regardless of custom URL
        fallback_base = DEFAULT_SEARXNG_URL.replace("localhost", "127.0.0.1")
        urls.append(f"{fallback_base}/search")
    return urls


def get_searxng_base_url() -> str:
    """Return the configured SearXNG base URL."""
    return os.environ.get("SEARXNG_URL", DEFAULT_SEARXNG_URL).rstrip("/")


async def get_discovery_client(
    base_url: str | None = None,
    source_type: Optional[SourceType] = None,
) -> tuple[DiscoveryClient, Optional[SourceType]]:
    """Get or create the shared discovery client."""
    global _default_client
    resolved_base = (base_url or get_searxng_base_url()).rstrip("/")
    
    if _default_client is not None and _default_client.base_url != resolved_base:
        reset_discovery_client()

    if _default_client is None:
        _default_client = DiscoveryClient(base_url=resolved_base)
    return _default_client, source_type


async def get_search_client(
    source_type: Optional[SourceType] = None,
) -> tuple[SearchClient, Optional[SourceType]]:
    """Factory: returns SearXNG when healthy, Perplexity when SearXNG is down or
    when OpenRouter key is available and SearXNG fails."""
    searxng_healthy = await _SEARXNG_CB.can_execute()

    # Strategy 1: SearXNG is healthy — try it first for raw source diversity
    if searxng_healthy:
        try:
            client, resolved_type = await get_discovery_client(source_type=source_type)
            # Quick health check: perform a lightweight search
            health_results = await client.search("test", num_results=1)
            # Must return at least one result to be considered truly healthy
            if health_results:
                return client, resolved_type
            logger.warning("SearXNG health check returned 0 results — considering fallback")
        except Exception as exc:
            logger.warning("SearXNG health check failed (%s) — considering fallback", exc)

    # Strategy 2: SearXNG is down or unhealthy — use Perplexity if available
    if settings.OPENROUTER_API_KEY:
        logger.info("SearXNG circuit OPEN/unhealthy/empty — using Perplexity fallback")
        try:
            return PerplexitySearchClient(), source_type
        except ValueError:
            logger.warning("Perplexity client init failed — falling back to SearXNG")

    # Strategy 3: Last resort — return SearXNG even if circuit breaker suggests it's open.
    # The caller's error handling will deal with actual failures.
    return await get_discovery_client(source_type=source_type)
