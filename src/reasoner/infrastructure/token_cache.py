"""
Token-Aware Caching Module
Implements semantic caching with token-based eviction for maximum cost efficiency.

Features:
- Cache by (problem_hash, phase, model_id) for granular reuse
- Semantic similarity matching (85%+ similar = cache hit)
- Token-based eviction (LRU + token budget)
- TTL-based expiration
- Statistics tracking for cost analysis
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    key: str
    problem_hash: str
    phase: str
    model_id: str
    prompt_hash: str
    response: str
    tokens_used: int
    created_at: float
    ttl_seconds: int
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    semantic_embedding: list[float] | None = None  # For semantic matching
    raw_prompt: str = ""  # Stored for Jaccard semantic matching


@dataclass
class CacheStats:
    """Cache statistics for monitoring."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_tokens_saved: int = 0
    total_size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def estimated_cost_savings(self) -> float:
        # Approximate: $0.000001 per token (average across providers)
        return self.total_tokens_saved * 0.000001


class TokenAwareCache:
    """
    Token-aware cache with semantic matching and token-based eviction.
    
    Usage:
        cache = TokenAwareCache(max_tokens=1_000_000, ttl=3600)
        
        # Check cache
        cached = await cache.get(problem, phase, model_id, prompt)
        if cached:
            return cached  # Cache hit - saves tokens!
        
        # Call LLM
        response = await llm.call(...)
        
        # Store in cache
        await cache.set(problem, phase, model_id, prompt, response, tokens_used)
    """

    def __init__(
        self,
        max_tokens: int = 1_000_000,  # 1M token budget
        ttl_seconds: int = 3600,  # 1 hour default TTL
        cache_dir: Path | None = None,
        semantic_threshold: float = 0.85,  # 85% similarity for cache hit
        max_entries: int = 1000,
    ):
        self.max_tokens = max_tokens
        self.ttl_seconds = ttl_seconds
        self.cache_dir = cache_dir
        self.semantic_threshold = semantic_threshold
        self.max_entries = max_entries

        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lru_max_entries: int = 512  # LRU cap — oldest evicted on overflow
        self._current_tokens = 0
        self._stats = CacheStats()
        self._lock = asyncio.Lock()
        self._problem_index: dict[str, list[str]] = {}
        self._loaded = False

        # Defer disk loading — call _ensure_loaded() before first use
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    async def _ensure_loaded(self) -> None:
        """Lazy-init: load cache entries from disk on first use.

        BUG-016: _loaded must only be set on a successful load. get()/set()
        call this unguarded, so a raise here would crash a live cache lookup
        on a transient disk error — but marking _loaded=True unconditionally
        (the original bug) permanently disables the cache after that one
        error, since every later call sees _loaded=True and skips retrying.
        """
        if self._loaded or not self.cache_dir:
            return
        try:
            await self._load_from_disk()
            self._loaded = True
        except Exception as exc:
            logger.warning(
                "Token cache disk load failed, operating with empty cache: %s", exc
            )

    def _compute_key(self, problem: str, phase: str, model_id: str, prompt: str, agent_id: str = "") -> str:
        """Compute cache key. agent_id scopes the cache to a user/session."""
        content = f"{agent_id}:{problem}:{phase}:{model_id}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def _compute_prompt_hash(self, prompt: str) -> str:
        """Compute prompt hash for exact matching."""
        # Cache-key digest only, never a security boundary.
        return hashlib.md5(prompt.encode(), usedforsecurity=False).hexdigest()[:16]

    def _compute_problem_hash(self, problem: str) -> str:
        """Compute problem hash for grouping."""
        return hashlib.sha256(problem.encode()).hexdigest()[:16]

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough: 1 token ≈ 4 chars)."""
        return len(text) // 4

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two texts using word sets."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0

    async def get(
        self,
        problem: str,
        phase: str,
        model_id: str,
        prompt: str,
        semantic_threshold: float = 0.85,
        agent_id: str = "",
    ) -> str | None:
        """
        Get cached response.

        Checks exact match first, then falls back to Jaccard semantic similarity
        for near-miss prompts within the same problem group.

        Returns:
            Cached response if hit, None otherwise
        """
        async with self._lock:
            await self._ensure_loaded()
            key = self._compute_key(problem, phase, model_id, prompt, agent_id=agent_id)
            prompt_hash = self._compute_prompt_hash(prompt)

            # Check exact match first
            if key in self._entries:
                entry = self._entries[key]

                # Check TTL — use wall-clock time so TTL survives disk reload
                if time.time() - entry.created_at > entry.ttl_seconds:
                    await self._evict(key)
                    self._stats.misses += 1
                    return None

                # Exact prompt match — LRU promote
                if entry.prompt_hash == prompt_hash:
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    self._entries.move_to_end(key)  # LRU promotion
                    self._stats.hits += 1
                    self._stats.total_tokens_saved += entry.tokens_used
                    return entry.response

            # Check semantic similarity via problem_hash index (O(k) vs O(n))
            problem_hash = self._compute_problem_hash(problem)
            for ck in self._problem_index.get(problem_hash, []):
                entry = self._entries.get(ck)
                if entry is None or entry.phase != phase or entry.model_id != model_id:
                    continue

                # Exact prompt match within same problem group (fast path)
                if entry.prompt_hash == prompt_hash:
                    entry.access_count += 1
                    self._entries.move_to_end(ck)  # LRU promotion
                    entry.last_accessed = time.time()
                    self._stats.hits += 1
                    self._stats.total_tokens_saved += entry.tokens_used
                    return entry.response

                # Jaccard semantic similarity on raw prompts
                if entry.raw_prompt and self._jaccard_similarity(prompt, entry.raw_prompt) >= semantic_threshold:
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    self._stats.hits += 1
                    self._stats.total_tokens_saved += entry.tokens_used
                    return entry.response

            self._stats.misses += 1
            return None

    async def set(
        self,
        problem: str,
        phase: str,
        model_id: str,
        prompt: str,
        response: str,
        tokens_used: int,
        ttl_seconds: int | None = None,
        agent_id: str = "",
    ) -> None:
        """Store response in cache."""
        async with self._lock:
            await self._ensure_loaded()
            key = self._compute_key(problem, phase, model_id, prompt, agent_id=agent_id)

            # Check if we need to evict — token budget, max entries, or LRU cap
            while (self._current_tokens + tokens_used > self.max_tokens
                   or len(self._entries) >= self.max_entries
                   or len(self._entries) >= self._lru_max_entries):
                await self._evict_lru()

            # Create entry
            entry = CacheEntry(
                key=key,
                problem_hash=self._compute_problem_hash(problem),
                phase=phase,
                model_id=model_id,
                prompt_hash=self._compute_prompt_hash(prompt),
                response=response,
                tokens_used=tokens_used,
                created_at=time.time(),
                last_accessed=time.time(),
                ttl_seconds=ttl_seconds or self.ttl_seconds,
                raw_prompt=prompt,
            )

            # Subtract old entry's token count on overwrite to prevent counter leak
            if key in self._entries:
                old_entry = self._entries[key]
                self._current_tokens -= old_entry.tokens_used
                self._stats.total_size_bytes -= len(old_entry.response.encode())
                # Phase 2.8: remove old key from problem_index to prevent zombie entries
                old_idx = self._problem_index.get(old_entry.problem_hash)
                if old_idx:
                    try:
                        old_idx.remove(key)
                    except ValueError:
                        pass

            self._entries[key] = entry
            self._problem_index.setdefault(entry.problem_hash, []).append(key)
            self._current_tokens += tokens_used
            self._stats.total_size_bytes += len(response.encode())

            # Save to disk if cache_dir provided
            if self.cache_dir:
                await self._save_to_disk(key, entry)

    async def _evict(self, key: str) -> None:
        """Evict specific entry."""
        if key in self._entries:
            entry = self._entries[key]
            idx = self._problem_index.get(entry.problem_hash)
            if idx:
                try:
                    idx.remove(key)
                except ValueError:
                    pass
            self._current_tokens -= entry.tokens_used
            self._stats.total_size_bytes -= len(entry.response.encode())
            self._stats.evictions += 1
            del self._entries[key]

    async def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._entries:
            return

        # Find LRU entry
        lru_key = min(
            self._entries.keys(),
            key=lambda k: self._entries[k].last_accessed
        )
        await self._evict(lru_key)

    async def _cleanup_expired(self) -> int:
        """Evict all TTL-expired entries from memory and disk. Returns count removed."""
        now = time.time()
        expired = [
            key for key, entry in self._entries.items()
            if now - entry.created_at > entry.ttl_seconds
        ]
        for key in expired:
            await self._evict(key)
            # Also remove the on-disk JSON file (git#B-18)
            if self.cache_dir:
                f = self.cache_dir / f"{key}.json"
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
        if expired:
            logger.debug("Token cache: evicted %d expired entries", len(expired))
        return len(expired)

    async def start_background_cleanup(
        self, interval_seconds: int = 300
    ) -> asyncio.Task:
        """Start a background task that periodically evicts expired entries.

        Returns the Task so the caller can cancel it on shutdown.
        """

        async def _loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    async with self._lock:
                        await self._cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.warning("Token cache cleanup error: %s", exc)

        return asyncio.create_task(_loop(), name="token_cache_cleanup")

    async def clear(self) -> None:
        """Clear all cache entries and the statistics describing them."""
        async with self._lock:
            self._entries.clear()
            self._problem_index.clear()
            self._current_tokens = 0
            # Every counter, not just total_size_bytes. hits/misses/evictions/
            # total_tokens_saved all describe the population just dropped, so
            # leaving them makes get_stats() report a hit_rate and a savings
            # figure for a cache that no longer exists -- and, because
            # tests/conftest.py resets this singleton around every test, lets
            # one test's tallies show up in another's assertions.
            self._stats = CacheStats()

            # Clear disk cache
            if self.cache_dir:
                for f in self.cache_dir.glob("*.json"):
                    try:
                        f.unlink(missing_ok=True)
                    except PermissionError:
                        pass

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "entries": len(self._entries),
            "current_tokens": self._current_tokens,
            "max_tokens": self.max_tokens,
            "utilization": self._current_tokens / self.max_tokens if self.max_tokens > 0 else 0,
            "hits": self._stats.hits,
            "misses": self._stats.misses,
            "hit_rate": self._stats.hit_rate,
            "evictions": self._stats.evictions,
            "tokens_saved": self._stats.total_tokens_saved,
            "estimated_cost_savings_usd": self._stats.estimated_cost_savings,
        }

    async def _load_from_disk(self) -> None:
        """Load cache entries from disk."""
        if not self.cache_dir:
            return

        for f in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(await asyncio.to_thread(f.read_text))
                entry = CacheEntry(**data)

                # Skip expired entries — use wall-clock time for cross-process TTL
                if time.time() - entry.created_at > entry.ttl_seconds:
                    f.unlink()
                    continue

                self._entries[entry.key] = entry
                self._problem_index.setdefault(entry.problem_hash, []).append(entry.key)
                self._current_tokens += entry.tokens_used
            except (json.JSONDecodeError, KeyError, TypeError):
                # Corrupted file, remove it
                f.unlink()

    async def _save_to_disk(self, key: str, entry: CacheEntry) -> None:
        """Save entry to disk."""
        if not self.cache_dir:
            return

        f = self.cache_dir / f"{key}.json"
        try:
            data = {
                "key": entry.key,
                "problem_hash": entry.problem_hash,
                "phase": entry.phase,
                "model_id": entry.model_id,
                "prompt_hash": entry.prompt_hash,
                "response": entry.response,
                "tokens_used": entry.tokens_used,
                "created_at": entry.created_at,
                "ttl_seconds": entry.ttl_seconds,
                "access_count": entry.access_count,
                "last_accessed": entry.last_accessed,
                "raw_prompt": entry.raw_prompt,
            }
            await asyncio.to_thread(f.write_text, json.dumps(data))
        except OSError as exc:
            logger.warning("Failed to persist cache entry %s to disk: %s", key, exc)


# Global cache instance
_cache: TokenAwareCache | None = None


def get_token_cache(
    max_tokens: int | None = None,
    ttl_seconds: int | None = None,
    cache_dir: str | None = None,
) -> TokenAwareCache:
    """Get or create the global token-aware cache.

    Arguments configure the singleton only on the call that creates it; any
    later call returns the existing instance untouched, whatever it asks for.
    That is unavoidable for a process-wide singleton, but it used to be
    silent: application/pipeline.py builds it at import time with
    cache_dir="cache/tokens" while api/__init__.py's lifespan asks for one
    with no arguments, so whichever ran first decided whether disk
    persistence was on for the process and the loser got no indication. A
    conflicting request is now logged. Callers that need their own
    configuration should construct TokenAwareCache() directly instead of
    reaching for the singleton.

    None means "no opinion, use the instance defaults" for every argument.
    """
    global _cache
    if _cache is None:
        overrides: dict[str, Any] = {}
        if max_tokens is not None:
            overrides["max_tokens"] = max_tokens
        if ttl_seconds is not None:
            overrides["ttl_seconds"] = ttl_seconds
        if cache_dir is not None:
            overrides["cache_dir"] = Path(cache_dir)
        _cache = TokenAwareCache(**overrides)
        return _cache

    conflicts = []
    if max_tokens is not None and max_tokens != _cache.max_tokens:
        conflicts.append(f"max_tokens={max_tokens} (live: {_cache.max_tokens})")
    if ttl_seconds is not None and ttl_seconds != _cache.ttl_seconds:
        conflicts.append(f"ttl_seconds={ttl_seconds} (live: {_cache.ttl_seconds})")
    if cache_dir is not None and Path(cache_dir) != _cache.cache_dir:
        conflicts.append(f"cache_dir={Path(cache_dir)} (live: {_cache.cache_dir})")
    if conflicts:
        logger.warning(
            "get_token_cache() ignored the requested configuration -- the "
            "process-wide cache was already built by an earlier caller: %s. "
            "Construct TokenAwareCache() directly for an independently "
            "configured cache.",
            "; ".join(conflicts),
        )
    return _cache


async def reset_token_cache() -> None:
    """Resets the global token cache for testing purposes.

    Clears the existing instance in place rather than dropping the module
    singleton (`_cache = None`). Callers that captured a reference to the
    cache before this runs — e.g. `application/pipeline.py`'s module-level
    `token_cache = get_token_cache(...)`, bound once at import time — keep
    using that same object for the life of the process. Nulling `_cache`
    here only resets *this module's* pointer: the first reset after import
    empties it as intended, but every reset after that sees `_cache is
    None` and no-ops, while `pipeline.py` (and anything else holding an
    earlier reference) goes on serving stale cache hits for the rest of the
    test session. Clearing in place keeps every held reference — this
    module's and any captured earlier — pointing at the same emptied cache.

    It also detaches the singleton from disk first. The instance
    application/pipeline.py builds at import points at the real
    `cache/tokens/` directory in the working tree; clear() globs and unlinks
    every *.json in whatever directory it is given, and tests/conftest.py's
    autouse fixture runs this before *and* after every test. Running the
    suite therefore deleted a developer's genuine cached responses, ~2x per
    test, purely as a side effect. Dropping cache_dir takes the test process
    out of that directory entirely — nothing is read from it, nothing is
    written to it, nothing is deleted from it — which is also stronger
    isolation than the wipe was: no entry a test writes can survive on disk
    to be reloaded by _ensure_loaded() in a later session.
    """
    if _cache is not None:
        _cache.cache_dir = None
        await _cache.clear()
