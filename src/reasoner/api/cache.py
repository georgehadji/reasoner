from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
from pathlib import Path

try:
    from reasoner.metrics import REASONER_CACHE_HIT_RATE, REASONER_CACHE_ENTRIES
    _METRICS_AVAILABLE = True
except Exception:
    _METRICS_AVAILABLE = False

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# In-memory hot-cache layer to avoid disk I/O on repeated identical requests.
# NOTE: This is a per-process cache. For horizontal scaling, use Redis or
# a shared external cache.
_MEMORY_CACHE: dict[str, list[dict]] = {}
_MEMORY_CACHE_MAX_SIZE = 256
_memory_cache_lock = threading.Lock()
_cache_hits: int = 0
_cache_misses: int = 0
_cache_evictions: int = 0  # Track evictions for metric


def get_cache_stats() -> dict[str, int | float]:
    """Return memory cache telemetry."""
    total = _cache_hits + _cache_misses
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "evictions": _cache_evictions,
        "total": total,
        "hit_rate": (_cache_hits / total) if total > 0 else 0.0,
        "current_size": len(_MEMORY_CACHE),
        "max_size": _MEMORY_CACHE_MAX_SIZE,
    }


def _prune_memory_cache_locked() -> None:
    """FIFO eviction for the in-memory cache.

    Caller MUST already hold _memory_cache_lock. The lock is a non-reentrant
    threading.Lock, so re-acquiring it here would self-deadlock the caller.
    """
    global _cache_evictions
    # Back-compat: allow monkey-patching from importing modules (e.g. tests)
    max_size = _MEMORY_CACHE_MAX_SIZE
    try:
        import reasoner.api as _api
        max_size = getattr(_api, '_MEMORY_CACHE_MAX_SIZE', max_size)
    except Exception:
        pass
    excess = len(_MEMORY_CACHE) - max_size
    if excess > 0:
        for _ in range(excess):
            _MEMORY_CACHE.pop(next(iter(_MEMORY_CACHE)), None)
        _cache_evictions += excess
        if _METRICS_AVAILABLE:
            try:
                from reasoner.metrics import REASONER_CACHE_EVICTIONS
                REASONER_CACHE_EVICTIONS.set(_cache_evictions)
            except Exception:
                pass


def _prune_memory_cache() -> None:
    """Simple FIFO eviction for the in-memory cache (thread-safe)."""
    with _memory_cache_lock:
        _prune_memory_cache_locked()


def clear_memory_cache() -> None:
    """Clear the in-memory cache (thread-safe)."""
    with _memory_cache_lock:
        _MEMORY_CACHE.clear()


def _cache_key(req: "RunRequest", user_id: str | None = None) -> str:
    # v=7 includes user_id to prevent cross-tenant cache disclosure (D1)
    attachments_key = None
    if getattr(req, "attachments", None):
        attachments_key = [
            {"file_id": a.file_id, "text_hash": hashlib.sha256(a.extracted_text.encode()).hexdigest()[:16]}
            for a in req.attachments
        ]
    
    # For anonymous users with CACHE_SHARE_ANONYMOUS enabled, use a sentinel
    user_key = user_id
    if user_key is None:
        try:
            from reasoner.core.settings import settings
            if settings.CACHE_SHARE_ANONYMOUS:
                user_key = "__anonymous__"
        except Exception:
            user_key = None
    
    payload = json.dumps({
        "problem": req.problem,
        "preset":  req.preset,
        "top_k":   req.top_k,
        "routing": req.routing,
        "force_pipeline": req.force_pipeline,
        "sequential": req.sequential,
        "enhance_prompt": req.enhance_prompt,
        "expert": req.expert,
        "web_search": req.web_search,
        "smart_search": req.smart_search,
        "source_type": req.source_type,
        "domain": req.domain,
        "attachments": attachments_key,
        "user_id": user_key,
        "v": 7,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def _load_cache(key: str) -> list[dict] | None:
    global _cache_hits, _cache_misses
    # 1. Check in-memory hot cache first (under lock for consistency)
    with _memory_cache_lock:
        if key in _MEMORY_CACHE:
            _cache_hits += 1
            if _METRICS_AVAILABLE:
                total = _cache_hits + _cache_misses
                REASONER_CACHE_HIT_RATE.set(_cache_hits / total if total > 0 else 0.0)
                REASONER_CACHE_ENTRIES.set(len(_MEMORY_CACHE))
            return _MEMORY_CACHE[key]

    # 2. Fall back to disk
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        try:
            data = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
            with _memory_cache_lock:
                _MEMORY_CACHE[key] = data
                _prune_memory_cache_locked()
            return data
        except (json.JSONDecodeError, OSError):
            # Treat a corrupt or unreadable cache file as a cache miss and
            # remove it so the next run can write a clean file.
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    with _memory_cache_lock:
        _cache_misses += 1
        if _METRICS_AVAILABLE:
            total = _cache_hits + _cache_misses
            REASONER_CACHE_HIT_RATE.set(_cache_hits / total if total > 0 else 0.0)
            REASONER_CACHE_ENTRIES.set(len(_MEMORY_CACHE))
    return None


_MAX_CACHE_FILES: int = 1000


def _prune_disk_cache() -> None:
    """Remove oldest cache files if the directory exceeds the max size."""
    files = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    excess = len(files) - _MAX_CACHE_FILES
    for f in files[:excess]:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


async def _save_cache(key: str, events: list[dict]) -> None:
    # Update in-memory hot cache immediately (under lock)
    with _memory_cache_lock:
        _MEMORY_CACHE[key] = events.copy()
        _prune_memory_cache_locked()

    # Write to a sibling temp file then rename so that a crash during the
    # write never leaves a corrupt (partial) JSON file at the target path.
    # FIX BUG-007: Use unique temp filename per writer to prevent race conditions
    # on Windows where os.replace() is not atomic. Include PID and timestamp for uniqueness.
    path = CACHE_DIR / f"{key}.json"
    # Unique temp file: key.{pid}.{timestamp}.tmp
    tmp = CACHE_DIR / f"{key}.{os.getpid()}.{int(time.time() * 1000)}.tmp"
    try:
        await asyncio.to_thread(tmp.write_text, json.dumps(events), encoding="utf-8")
        # On Windows, os.replace() may not be atomic, but with unique temp filenames
        # we avoid overwriting another writer's temp file. The last writer wins,
        # but data is never corrupted from interleaved writes.
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return
    finally:
        # Clean up old temp files (crashed writers) regardless of success
        for old_tmp in CACHE_DIR.glob(f"{key}.*.tmp"):
            try:
                old_tmp.unlink(missing_ok=True)
            except OSError:
                pass
        _prune_disk_cache()
