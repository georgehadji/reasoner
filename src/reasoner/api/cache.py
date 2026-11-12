from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from reasoner.core.settings import settings as _settings
from reasoner.infrastructure.persistence.history_files import owner_key
from reasoner.utils.atomic_file import atomic_write_text

if TYPE_CHECKING:
    from reasoner.api.schemas import RunRequest

try:
    from reasoner.metrics import REASONER_CACHE_ENTRIES, REASONER_CACHE_HIT_RATE
    _METRICS_AVAILABLE = True
except Exception:
    _METRICS_AVAILABLE = False

# Unset keeps the in-package default for local dev; a deployment points it at a
# mounted volume, because the package dir is replaced on every redeploy.
CACHE_DIR = (
    Path(_settings.RUN_CACHE_DIR)
    if _settings.RUN_CACHE_DIR
    else Path(__file__).parent.parent / "cache"
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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


def _mem_key(key: str, user_id: str | None) -> str:
    # An owner's entries share a prefix, so erasing one owner drops exactly them.
    return f"{owner_key(user_id)}:{key}" if user_id else key


def _disk_path(key: str, user_id: str | None) -> Path:
    """Owned entries live in their owner's directory, so erasure is one rmtree.
    Anonymous entries stay flat: there is no owner to erase them for."""
    return (CACHE_DIR / owner_key(user_id) if user_id else CACHE_DIR) / f"{key}.json"


def _owner_files(user_id: str) -> list[Path]:
    folder = CACHE_DIR / owner_key(user_id)
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def export_owner_cache(user_id: str) -> list[dict]:
    """The owner's cached runs (problem and synthesis events), for GDPR export."""
    runs: list[dict] = []
    for path in _owner_files(user_id):
        try:
            runs.append({"key": path.stem, "events": json.loads(path.read_text(encoding="utf-8"))})
        except (OSError, json.JSONDecodeError):
            # Unreadable is still the owner's data; say so rather than shorten the export.
            runs.append({"key": path.stem, "events": None, "unreadable": True})
    return runs


def erase_owner_cache(user_id: str) -> int:
    """Delete the owner's replay cache from disk and from this process's memory.

    Returns the number of files that could not be removed. Other workers keep
    their own in-memory copy until it is evicted; there is no shared channel to
    tell them (the disk copy, which they reload from, is gone).
    """
    prefix = f"{owner_key(user_id)}:"
    with _memory_cache_lock:
        for k in [k for k in _MEMORY_CACHE if k.startswith(prefix)]:
            del _MEMORY_CACHE[k]
    folder = CACHE_DIR / owner_key(user_id)
    failed = 0
    for path in list(folder.iterdir()) if folder.is_dir() else []:
        try:
            path.unlink()
        except OSError:
            failed += 1
    try:
        folder.rmdir()
    except OSError:
        pass
    return failed


def clear_disk_cache() -> int:
    """Remove every cached run, anonymous and owned. Returns how many files."""
    cleared = 0
    for f in [*CACHE_DIR.glob("*.json"), *CACHE_DIR.glob("u-*/*.json")]:
        try:
            f.unlink(missing_ok=True)
            cleared += 1
        except OSError:
            pass
    return cleared


def clear_memory_cache() -> None:
    """Clear the in-memory cache (thread-safe)."""
    with _memory_cache_lock:
        _MEMORY_CACHE.clear()


def _cache_key(req: RunRequest, user_id: str | None = None) -> str:
    # v=7 includes user_id to prevent cross-tenant cache disclosure (D1)
    attachments_key = None
    if getattr(req, "attachments", None):
        attachments_key = [
            {
                "file_id": a.file_id,
                "text_hash": hashlib.sha256(a.extracted_text.encode()).hexdigest()[:16],
            }
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
        # file_ids drive prism file search; without them a run over file B
        # replayed the cached answer about file A.
        "file_ids": sorted(getattr(req, "file_ids", None) or []),
        "user_id": user_key,
        "v": 7,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def _load_cache(key: str, user_id: str | None = None) -> list[dict] | None:
    global _cache_hits, _cache_misses
    mem_key = _mem_key(key, user_id)
    # 1. Check in-memory hot cache first (under lock for consistency)
    with _memory_cache_lock:
        if mem_key in _MEMORY_CACHE:
            _cache_hits += 1
            if _METRICS_AVAILABLE:
                total = _cache_hits + _cache_misses
                REASONER_CACHE_HIT_RATE.set(_cache_hits / total if total > 0 else 0.0)
                REASONER_CACHE_ENTRIES.set(len(_MEMORY_CACHE))
            return _MEMORY_CACHE[mem_key]

    # 2. Fall back to disk
    path = _disk_path(key, user_id)
    if path.exists():
        try:
            data = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8"))
            with _memory_cache_lock:
                _MEMORY_CACHE[mem_key] = data
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
    files = sorted(
        [*CACHE_DIR.glob("*.json"), *CACHE_DIR.glob("u-*/*.json")], key=lambda p: p.stat().st_mtime
    )
    excess = len(files) - _MAX_CACHE_FILES
    for f in files[:excess]:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


async def _save_cache(key: str, events: list[dict], user_id: str | None = None) -> None:
    # Update in-memory hot cache immediately (under lock)
    with _memory_cache_lock:
        _MEMORY_CACHE[_mem_key(key, user_id)] = events.copy()
        _prune_memory_cache_locked()

    # A crash during the write never leaves a partial JSON file at the
    # target path, and each writer has its own temp file (BUG-007): the last
    # writer wins, but data is never corrupted from interleaved writes.
    path = _disk_path(key, user_id)
    try:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(atomic_write_text, path, json.dumps(events))
    except OSError:
        return
    finally:
        # Clean up old temp files (crashed writers) regardless of success
        for old_tmp in path.parent.glob(f"{key}.json.*.tmp"):
            try:
                old_tmp.unlink(missing_ok=True)
            except OSError:
                pass
        _prune_disk_cache()
