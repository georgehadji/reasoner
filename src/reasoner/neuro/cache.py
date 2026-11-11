"""
Neuro Cache Hierarchy
L1/L2/L3 with persona-aware similarity thresholds.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple

import numpy as np

from reasoner.core.degrade import degraded
from reasoner.neuro.config import CacheConfig, PersonaConfig
from reasoner.utils.atomic_file import atomic_write_text, locked, read_json_or_quarantine

log = logging.getLogger("neuro.cache")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(dot / norm) if norm > 0 else 0.0


class ContextChunk:
    def __init__(self, content: str, source: str, relevance: float, cache_tier: str,
                 metadata: dict | None = None):
        self.content = content
        self.source = source
        self.relevance = relevance
        self.cache_tier = cache_tier
        # Provenance written at learn time (schema_version, run_id, ...). Recall
        # drops chunks without it, so dropping it here emptied every recall
        # (docs/plans/audit-remediation-2026-10-20.md DAT-4).
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {"content": self.content, "source": self.source,
                "relevance": round(self.relevance, 4), "cache_tier": self.cache_tier,
                "metadata": self.metadata}


class _Snapshot(NamedTuple):
    """One consistent view of a tier, swapped in whole so a search never sees half an update."""

    stamp: object  # what the backing file(s) looked like when read; any write changes it
    items: list[dict]  # every entry, in eviction order
    rows: list[dict]  # items that carry an embedding, in matrix row order
    unit: np.ndarray  # rows' embeddings scaled to length 1, so cosine is one mat-vec
    lines: int = 0  # L2 only: records in index.jsonl, superseded ones included


def _snapshot(stamp: object, items: list[dict], lines: int = 0) -> _Snapshot:
    rows = [i for i in items if i.get("embedding")]
    unit = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
    if rows:
        unit /= np.maximum(np.linalg.norm(unit, axis=1, keepdims=True), 1e-12)
    return _Snapshot(stamp, items, rows, unit, lines)


def _cosines(snap: _Snapshot, query: list[float]) -> np.ndarray:
    """cosine_similarity(query, row) for every row, without a Python loop (LI-01)."""
    if not snap.rows:
        return np.zeros(0, dtype=np.float32)
    q = np.asarray(query, dtype=np.float32)
    norm = float(np.linalg.norm(q))
    return snap.unit @ (q / norm) if norm > 0 else np.zeros(len(snap.rows), dtype=np.float32)


def _best(
    snap: _Snapshot, sims: np.ndarray, keep: np.ndarray, top_k: int
) -> list[tuple[float, dict]]:
    hits = np.flatnonzero(keep)
    hits = hits[np.argsort(-sims[hits], kind="stable")][:top_k]
    return [(float(sims[i]), snap.rows[i]) for i in hits]


class L1Cache:
    _snap: _Snapshot

    def __init__(self, cache_dir: Path, config: CacheConfig):
        self.cache_dir = cache_dir
        self.config = config
        self._load()

    @property
    def bundles(self) -> list[dict]:
        return self._snap.items

    def _stamp(self) -> frozenset | None:
        # Name, size and mtime of every bundle file, so another worker's add or
        # eviction shows up. A directory mtime alone misses two writes that
        # land inside one coarse filesystem clock tick.
        try:
            with os.scandir(self.cache_dir) as it:
                files = [e for e in it if e.name.endswith(".json")]
        except FileNotFoundError:
            return None
        sig = set()
        for e in files:
            try:
                st = e.stat()
            except FileNotFoundError:
                continue
            sig.add((e.name, st.st_mtime_ns, st.st_size))
        return frozenset(sig)

    def _read(self) -> _Snapshot:
        # Stamp before reading: a write that lands mid-read shows as a change next time.
        stamp = self._stamp()
        bundles = []
        for f in sorted(self.cache_dir.glob("*.json")):
            try:
                bundles.append(json.loads(f.read_text()))
            except Exception as e:
                log.warning(f"L1 load error {f}: {e}")
        return _snapshot(stamp, bundles)

    def _load(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._snap = self._read()
        log.info(f"L1 cache: {len(self.bundles)} bundles")

    def _refresh(self) -> _Snapshot:
        # Each uvicorn worker holds its own copy of a tenant; without this a
        # learn in one worker stayed invisible to recall in the other (RB-01).
        if self._stamp() != self._snap.stamp:
            self._snap = self._read()
        return self._snap

    def search(self, query_embedding: list[float], top_k: int = 3,
               persona: PersonaConfig | None = None) -> list[ContextChunk]:
        threshold = self.config.l1_similarity_threshold
        if persona and persona.l1_similarity_override is not None:
            threshold = persona.l1_similarity_override

        snap = self._refresh()
        sims = _cosines(snap, query_embedding)
        age = time.time() - np.array([b.get("created_at", 0) for b in snap.rows], dtype=np.float64)
        keep = (sims >= threshold) & (age <= self.config.l1_ttl_seconds)
        return [ContextChunk(b["content"], b.get("source", "l1-cache"), s, "L1",
                             b.get("metadata"))
                for s, b in _best(snap, sims, keep, top_k)]

    async def add(self, content: str, source: str, embedding: list[float],
                  metadata: dict | None = None) -> str:
        # metadata is the learn-time provenance. Without it every L1 hit failed
        # recall's schema_version filter, yet still took a recall slot (PER-10).
        bundle_id = hashlib.sha256(content.encode()).hexdigest()[:12]
        bundle = {"id": bundle_id, "content": content, "source": source,
                  "embedding": embedding, "metadata": metadata or {},
                  "created_at": time.time()}

        def _write() -> _Snapshot:
            # The lock serialises writers across workers, so the stamp taken
            # after our write cannot cover another worker's unread write.
            with locked(self.cache_dir / "bundles"):
                snap = self._snap if self._stamp() == self._snap.stamp else self._read()
                # bundle_id is a digest of the content, and one id maps to one file --
                # so re-adding identical content must replace, not append. Appending
                # put two entries in self.bundles behind a single file: search()
                # returned the same memory twice (burning top_k slots), and evicting
                # either copy unlinked the file while the other stayed "present" in
                # memory, so the entry vanished on the next _load().
                bundles = [b for b in snap.items if b.get("id") != bundle_id] + [bundle]
                excess = len(bundles) - self.config.l1_max_bundles
                if excess > 0:
                    bundles.sort(key=lambda b: b.get("created_at", 0))
                    for evicted in bundles[:excess]:
                        (self.cache_dir / f"{evicted['id']}.json").unlink(missing_ok=True)
                    bundles = bundles[excess:]
                path = self.cache_dir / f"{bundle_id}.json"
                atomic_write_text(path, json.dumps(bundle, default=str))
                return _snapshot(self._stamp(), bundles)

        self._snap = await asyncio.to_thread(_write)
        return bundle_id

    @property
    def size(self) -> int:
        return len(self.bundles)


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    """Records of *path* in file order, and how many lines could not be read."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], 0
    records: list[dict] = []
    bad = 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            bad += 1
    return records, bad


def _last_wins(records: list[dict], limit: int | None = None) -> list[dict]:
    """One record per id (the latest write), oldest first; keep only the newest *limit*."""
    by_id: dict = {}
    for record in records:
        by_id.pop(record.get("id"), None)
        by_id[record.get("id")] = record
    out = list(by_id.values())
    return out if limit is None else out[max(0, len(out) - limit):]


def _jsonl(records: list[dict]) -> str:
    return "".join(json.dumps(r, default=str) + "\n" for r in records)


def read_l2_entries(index_dir: Path) -> list[dict]:
    """Every L2 record on disk under *index_dir*, read-only.

    For callers that must see the data without loading or migrating an index
    (GDPR export): it includes a tenant's not-yet-migrated index.json.
    """
    legacy = index_dir / "index.json"
    old = json.loads(legacy.read_text(encoding="utf-8")) if legacy.exists() else []
    records, _ = _read_jsonl(index_dir / "index.jsonl")
    return _last_wins([*old, *records])


class L2Index:
    """Append-only JSONL index: a learn writes one line, not the whole index (LI-02)."""

    _snap: _Snapshot

    def __init__(self, index_dir: Path, config: CacheConfig):
        self.index_dir = index_dir
        self.config = config
        self._load()

    @property
    def _path(self) -> Path:
        return self.index_dir / "index.jsonl"

    @property
    def entries(self) -> list[dict]:
        return self._snap.items

    def _stamp(self) -> tuple[int, int] | None:
        # Every append grows the file and compaction roughly halves it, so the
        # size changes on each write even inside one filesystem clock tick.
        try:
            st = self._path.stat()
        except FileNotFoundError:
            return None
        return st.st_mtime_ns, st.st_size

    def _read(self) -> _Snapshot:
        # Stamp before reading: a write that lands mid-read shows as a change next time.
        stamp = self._stamp()
        records, bad = _read_jsonl(self._path)
        if bad:
            # A line torn by a crash mid-append. Only that line is lost; the
            # next compaction drops it from the file.
            exc = ValueError(f"{bad} unreadable lines in {self._path}")
            degraded("neuro.l2_index", None, exc=exc)
        return _snapshot(stamp, _last_wins(records, self.config.l2_max_entries), len(records))

    def _migrate(self, legacy: Path) -> None:
        """Fold a pre-JSONL index.json into index.jsonl; safe if another worker got there first."""
        with locked(self._path):
            # A corrupt file used to load as [] and the next add saved over it,
            # wiping the tenant's memory. It is now moved aside instead (PER-10).
            old: object
            old, quarantined = read_json_or_quarantine(legacy, [])
            if quarantined:
                degraded("neuro.l2_index", None, exc=ValueError(f"corrupt {legacy} quarantined"))
            records, _ = _read_jsonl(self._path)
            merged = [*(old if isinstance(old, list) else []), *records]
            atomic_write_text(self._path, _jsonl(_last_wins(merged, self.config.l2_max_entries)))
            legacy.unlink(missing_ok=True)

    def _load(self):
        self.index_dir.mkdir(parents=True, exist_ok=True)
        legacy = self.index_dir / "index.json"
        if legacy.exists():
            self._migrate(legacy)
        self._snap = self._read()
        log.info(f"L2 index: {len(self.entries)} entries")

    def _refresh(self) -> _Snapshot:
        # Same cross-worker staleness as L1Cache._refresh (RB-01).
        # shortcut: a reload re-parses the whole file on the event loop (~180 ms
        # at 500 entries); read only the appended tail if tenants get that big.
        if self._stamp() != self._snap.stamp:
            self._snap = self._read()
        return self._snap

    def search(self, query_embedding: list[float], top_k: int = 5,
               persona: PersonaConfig | None = None) -> list[ContextChunk]:
        threshold = self.config.l2_similarity_threshold
        if persona and persona.l2_similarity_override is not None:
            threshold = persona.l2_similarity_override

        snap = self._refresh()
        sims = _cosines(snap, query_embedding)
        return [ContextChunk(e["content"], e.get("source", "l2-memory"), s, "L2",
                             e.get("metadata"))
                for s, e in _best(snap, sims, sims > threshold, top_k)]

    async def add(self, content: str, source: str, embedding: list[float],
                  metadata: dict = None) -> str:
        entry_id = hashlib.sha256(content.encode()).hexdigest()[:12]
        entry = {"id": entry_id, "content": content, "source": source,
                 "embedding": embedding, "metadata": metadata or {},
                 "created_at": time.time()}

        def _append() -> _Snapshot:
            # Re-read inside the file lock when another worker (or a second
            # instance) wrote since our load, so its entries are kept, not
            # dropped from our view. The id is a content digest, so re-adding
            # the same content replaces it instead of duplicating.
            with locked(self._path):
                snap = self._snap if self._stamp() == self._snap.stamp else self._read()
                entries = _last_wins([*snap.items, entry], self.config.l2_max_entries)
                lines = snap.lines + 1
                if lines > 2 * self.config.l2_max_entries:
                    # Compact: drop superseded and evicted records.
                    atomic_write_text(self._path, _jsonl(entries))
                    lines = len(entries)
                else:
                    with open(self._path, "a", encoding="utf-8") as f:
                        # The leading newline fences off a line torn by a crash.
                        f.write("\n" + json.dumps(entry, default=str) + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                return _snapshot(self._stamp(), entries, lines)

        self._snap = await asyncio.to_thread(_append)
        return entry_id

    @property
    def size(self) -> int:
        return len(self.entries)


async def l3_scan(
    memory_dir: Path,
    query_embedding: list[float],
    embed_fn: Callable[[str], Awaitable[list[float]]],
    threshold: float = 0.4,
    top_k: int = 3,
) -> list[ContextChunk]:
    """
    Scan L3 (cold) memory files for relevant context.

    Embeddings are cached as sidecar .emb.json files alongside each memory file
    so that repeated scans never re-call the embedding provider for unchanged content.
    """
    memory_dir.mkdir(parents=True, exist_ok=True)
    sidecar_dir = memory_dir / ".emb_cache"
    sidecar_dir.mkdir(exist_ok=True)

    results = []
    for mem_file in sorted(memory_dir.glob("*.json")):
        try:
            mem = json.loads(await asyncio.to_thread(mem_file.read_text))
            content = mem.get("summary", "") + "\n" + "\n".join(mem.get("key_facts", []))
            if not content.strip():
                continue

            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            sidecar = sidecar_dir / f"{mem_file.stem}.emb.json"

            content_embedding = None
            if sidecar.exists():
                try:
                    cached = json.loads(await asyncio.to_thread(sidecar.read_text))
                    if cached.get("hash") == content_hash:
                        content_embedding = cached["embedding"]
                except Exception:
                    pass

            if content_embedding is None:
                content_embedding = await embed_fn(content)
                try:
                    await asyncio.to_thread(sidecar.write_text, json.dumps({"hash": content_hash, "embedding": content_embedding}))
                except Exception as e:
                    log.debug(f"L3 sidecar write failed for {mem_file.stem}: {e}")

            sim = cosine_similarity(query_embedding, content_embedding)
            if sim > threshold:
                results.append(ContextChunk(content, f"l3-scan:{mem_file.stem}", sim, "L3"))
        except Exception as e:
            log.warning(f"L3 error {mem_file}: {e}")
    results.sort(key=lambda x: x.relevance, reverse=True)
    return results[:top_k]
