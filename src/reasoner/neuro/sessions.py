"""
Neuro Session Manager
The Live Wire — captures every prompt/response as it happens.
No manual save required. If the plug gets pulled, everything is already on disk.

Lifecycle:
  Hot (days 1-3):   Raw session logs, instantly searchable
  Warm (days 4-29): Summarized, embedded, indexed in L2. Raw logs compressed.
  Cold (day 30+):   Compressed archive, L3 scan only.
"""

import asyncio
import gzip
import hashlib
import inspect
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger("neuro.sessions")


@dataclass
class SessionEntry:
    """A single prompt/response exchange."""

    timestamp: str
    prompt: str
    response: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionConfig:
    """Session lifecycle configuration."""

    hot_days: int = 3  # days before archival
    warm_days: int = 30  # days before cold storage
    max_session_gap_minutes: int = 60  # new session after this gap
    auto_summarize: bool = True  # summarize on archival
    max_hot_entries: int = 500  # safety cap per session file


class SessionManager:
    """
    Manages live session capture and lifecycle.

    Directory structure per agent:
      sessions/
        hot/
          2026-03-05_session-abc123.jsonl     ← live, appending
          2026-03-05_session-def456.jsonl
        warm/
          2026-03-02_session-xyz789.json      ← summarized
          2026-03-02_session-xyz789.jsonl.gz  ← compressed raw
        cold/
          2026-02-01_session-old001.jsonl.gz  ← deep archive
    """

    def __init__(self, data_dir: Path, config: SessionConfig | None = None):
        self.data_dir = data_dir
        self.config = config or SessionConfig()
        self.hot_dir = data_dir / "sessions" / "hot"
        self.warm_dir = data_dir / "sessions" / "warm"
        self.cold_dir = data_dir / "sessions" / "cold"

        for d in [self.hot_dir, self.warm_dir, self.cold_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._current_session_id: str | None = None
        self._current_session_file: Path | None = None
        self._last_ingest_time: float = 0
        self._entry_count: int = 0

        # Per-file write locks to prevent JSONL corruption under concurrency
        self._file_locks: dict[str, asyncio.Lock] = {}
        self._file_locks_meta = asyncio.Lock()

        # Entry-count cache: path → count, invalidated on ingest
        self._counts_cache: dict[str, int] = {}

    def _generate_session_id(self) -> str:
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        suffix = hashlib.sha256(str(time.time()).encode()).hexdigest()[:6]
        return f"{ts}_{suffix}"

    def _should_start_new_session(self) -> bool:
        if not self._current_session_id:
            return True
        if self._last_ingest_time == 0:
            return True
        gap = time.monotonic() - self._last_ingest_time
        return gap > (self.config.max_session_gap_minutes * 60)

    def _start_session(self) -> str:
        session_id = self._generate_session_id()
        self._current_session_id = session_id
        self._current_session_file = self.hot_dir / f"{session_id}.jsonl"
        self._entry_count = 0

        header = {
            "_type": "session_start",
            "session_id": session_id,
            "started_at": datetime.now(UTC).isoformat(),
        }
        with open(self._current_session_file, "a") as f:
            f.write(json.dumps(header) + "\n")

        log.info(f"Session started: {session_id}")
        return session_id

    async def _get_file_lock(self, path: Path) -> asyncio.Lock:
        key = str(path)
        async with self._file_locks_meta:
            if key not in self._file_locks:
                self._file_locks[key] = asyncio.Lock()
            return self._file_locks[key]

    def ingest(self, prompt: str, response: str, metadata: dict | None = None) -> dict:
        """
        Ingest a prompt/response pair into the current session.
        This is the Live Wire — fast, append-only, crash-safe.

        Note: file-level lock is acquired synchronously here; callers running in
        async contexts should use ingest_async() to avoid blocking the event loop.
        """
        try:
            if self._should_start_new_session():
                self._start_session()

            if self._entry_count >= self.config.max_hot_entries:
                self._start_session()

            entry = {
                "_type": "exchange",
                "timestamp": datetime.now(UTC).isoformat(),
                "prompt": prompt,
                "response": response,
                "metadata": metadata or {},
            }

            with open(self._current_session_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()

            self._last_ingest_time = time.monotonic()
            self._entry_count += 1

            # Invalidate count cache for this file
            self._counts_cache.pop(str(self._current_session_file), None)

            return {
                "session_id": self._current_session_id,
                "entry_number": self._entry_count,
                "session_file": str(self._current_session_file.name),
            }
        except OSError as e:
            log.error(f"Failed to write to session file {self._current_session_file}: {e}")
            raise
        except (TypeError, ValueError) as e:
            log.error(f"Failed to serialize session entry: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error ingesting session entry: {e}")
            raise RuntimeError(f"Failed to ingest session: {e}") from e

    async def ingest_async(
        self, prompt: str, response: str, metadata: dict | None = None
    ) -> dict:
        """
        Async variant of ingest — acquires a per-file asyncio.Lock before writing
        to prevent interleaved writes under concurrent callers.

        _start_session() is itself a synchronous file write (it writes the
        session-start header), so it is offloaded via asyncio.to_thread here
        too -- otherwise every session's first message would still block the
        event loop despite the exchange write below being async-safe.
        """
        try:
            if self._should_start_new_session():
                await asyncio.to_thread(self._start_session)

            if self._entry_count >= self.config.max_hot_entries:
                await asyncio.to_thread(self._start_session)

            entry = {
                "_type": "exchange",
                "timestamp": datetime.now(UTC).isoformat(),
                "prompt": prompt,
                "response": response,
                "metadata": metadata or {},
            }

            lock = await self._get_file_lock(self._current_session_file)
            async with lock:
                await asyncio.to_thread(self._write_entry, self._current_session_file, entry)

            self._last_ingest_time = time.monotonic()
            self._entry_count += 1
            self._counts_cache.pop(str(self._current_session_file), None)

            return {
                "session_id": self._current_session_id,
                "entry_number": self._entry_count,
                "session_file": str(self._current_session_file.name),
            }
        except OSError as e:
            log.error(f"Failed to write to session file {self._current_session_file}: {e}")
            raise
        except (TypeError, ValueError) as e:
            log.error(f"Failed to serialize session entry: {e}")
            raise
        except Exception as e:
            log.error(f"Unexpected error ingesting session entry: {e}")
            raise RuntimeError(f"Failed to ingest session: {e}") from e

    @staticmethod
    def _write_entry(path: Path, entry: dict):
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()

    def get_hot_sessions(self) -> list[dict]:
        """List all hot session files with stats."""
        sessions = []
        for f in sorted(self.hot_dir.glob("*.jsonl"), reverse=True):
            entries = self._count_entries(f)
            stat = f.stat()
            sessions.append(
                {
                    "session_id": f.stem,
                    "file": f.name,
                    "entries": entries,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    "tier": "hot",
                }
            )
        return sessions

    def get_warm_sessions(self) -> list[dict]:
        """List warm (summarized) sessions."""
        sessions = []
        for f in sorted(self.warm_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                sessions.append(
                    {
                        "session_id": f.stem,
                        "summary": data.get("summary", "")[:100],
                        "key_facts": len(data.get("key_facts", [])),
                        "tier": "warm",
                    }
                )
            except Exception:
                pass
        return sessions

    def search_hot(self, query: str, max_results: int = 10) -> list[dict]:
        """
        Search hot session logs via simple text matching.
        Fast but not semantic — for hot data, speed > precision.
        """
        query_lower = query.lower()
        results = []

        for session_file in sorted(self.hot_dir.glob("*.jsonl"), reverse=True):
            try:
                with open(session_file) as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            if entry.get("_type") != "exchange":
                                continue
                            text = f"{entry.get('prompt', '')} {entry.get('response', '')}"
                            if query_lower in text.lower():
                                results.append(
                                    {
                                        "session_id": session_file.stem,
                                        "timestamp": entry.get("timestamp", ""),
                                        "prompt": entry["prompt"][:200],
                                        "response": entry["response"][:200],
                                        "tier": "hot",
                                    }
                                )
                                if len(results) >= max_results:
                                    return results
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                log.warning(f"Hot search error on {session_file}: {e}")

        return results

    async def get_session_transcript_async(self, session_id: str) -> list[dict]:
        """Async version of get_session_transcript — uses asyncio.to_thread for I/O."""
        hot_file = self.hot_dir / f"{session_id}.jsonl"
        if hot_file.exists():
            return await asyncio.to_thread(self._read_jsonl, hot_file)

        warm_gz = self.warm_dir / f"{session_id}.jsonl.gz"
        if warm_gz.exists():
            return await asyncio.to_thread(self._read_jsonl_gz, warm_gz)

        cold_gz = self.cold_dir / f"{session_id}.jsonl.gz"
        if cold_gz.exists():
            return await asyncio.to_thread(self._read_jsonl_gz, cold_gz)

        return []

    def get_session_transcript(self, session_id: str) -> list[dict]:
        """Get full transcript of a session."""
        hot_file = self.hot_dir / f"{session_id}.jsonl"
        if hot_file.exists():
            return self._read_jsonl(hot_file)

        warm_gz = self.warm_dir / f"{session_id}.jsonl.gz"
        if warm_gz.exists():
            return self._read_jsonl_gz(warm_gz)

        cold_gz = self.cold_dir / f"{session_id}.jsonl.gz"
        if cold_gz.exists():
            return self._read_jsonl_gz(cold_gz)

        return []

    async def archive_hot_sessions(self, summarize_fn: Callable | None = None) -> list[dict]:
        """
        Move expired hot sessions to warm storage.
        Optionally summarize them using the reasoning provider.
        Returns list of archived sessions.

        summarize_fn may be sync or async.
        """
        cutoff = datetime.now(UTC) - timedelta(days=self.config.hot_days)
        archived = []

        for session_file in list(self.hot_dir.glob("*.jsonl")):
            if self._current_session_file and session_file == self._current_session_file:
                continue

            stat = session_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            if modified >= cutoff:
                continue

            session_id = session_file.stem
            entries = await asyncio.to_thread(self._read_jsonl, session_file)
            exchanges = [e for e in entries if e.get("_type") == "exchange"]

            if not exchanges:
                session_file.unlink()
                continue

            # Compress raw log to warm (offload gzip to thread)
            gz_path = self.warm_dir / f"{session_id}.jsonl.gz"
            await asyncio.to_thread(self._write_gzip, gz_path, entries)

            summary_data = {
                "session_id": session_id,
                "archived_at": datetime.now(UTC).isoformat(),
                "exchange_count": len(exchanges),
                "first_exchange": exchanges[0].get("timestamp", ""),
                "last_exchange": exchanges[-1].get("timestamp", ""),
                "summary": "",
                "key_facts": [],
            }

            if summarize_fn and self.config.auto_summarize:
                try:
                    transcript = "\n".join(
                        f"User: {e['prompt']}\nAssistant: {e['response']}" for e in exchanges[-20:]
                    )
                    if inspect.iscoroutinefunction(summarize_fn):
                        summary_result = await summarize_fn(transcript)
                    else:
                        summary_result = await asyncio.to_thread(summarize_fn, transcript)

                    if isinstance(summary_result, dict):
                        summary_data["summary"] = summary_result.get("summary", "")
                        summary_data["key_facts"] = summary_result.get("key_facts", [])
                    else:
                        summary_data["summary"] = str(summary_result)
                except Exception as e:
                    log.warning(f"Summarization failed for {session_id}: {e}")
                    summary_data["summary"] = f"[Auto-summary failed: {str(e)[:50]}]"

            summary_path = self.warm_dir / f"{session_id}.json"
            summary_path.write_text(json.dumps(summary_data, indent=2))

            session_file.unlink()
            # Remove stale count cache entry
            self._counts_cache.pop(str(session_file), None)
            archived.append(summary_data)
            log.info(f"Archived session {session_id}: {len(exchanges)} exchanges → warm")

        return archived

    def archive_warm_to_cold(self) -> list[str]:
        """Move expired warm sessions to cold storage."""
        cutoff = datetime.now(UTC) - timedelta(days=self.config.warm_days)
        moved = []

        for gz_file in list(self.warm_dir.glob("*.jsonl.gz")):
            stat = gz_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            if modified >= cutoff:
                continue

            session_id = gz_file.stem.replace(".jsonl", "")
            dest = self.cold_dir / gz_file.name
            gz_file.rename(dest)

            summary = self.warm_dir / f"{session_id}.json"
            if summary.exists():
                summary.rename(self.cold_dir / summary.name)

            moved.append(session_id)
            log.info(f"Cold archived: {session_id}")

        return moved

    def get_recent_context(self, n_exchanges: int = 20) -> str:
        """
        Get the most recent N exchanges across hot sessions.
        Used for context injection on bootstrap.
        """
        all_exchanges = []

        for session_file in sorted(self.hot_dir.glob("*.jsonl"), reverse=True):
            entries = self._read_jsonl(session_file)
            exchanges = [e for e in entries if e.get("_type") == "exchange"]
            all_exchanges.extend(exchanges)
            if len(all_exchanges) >= n_exchanges:
                break

        all_exchanges.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        recent = all_exchanges[:n_exchanges]
        recent.reverse()

        if not recent:
            return ""

        lines = []
        for e in recent:
            ts = e.get("timestamp", "")[:16]
            lines.append(f"[{ts}] User: {e.get('prompt', '')[:300]}")
            lines.append(f"[{ts}] Agent: {e.get('response', '')[:300]}")
            lines.append("")

        return "\n".join(lines)

    def list_recent_entries(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Return recent exchange entries across hot sessions, paginated.

        Results are sorted by timestamp descending (newest first).
        """
        all_exchanges: list[dict] = []
        for session_file in sorted(self.hot_dir.glob("*.jsonl"), reverse=True):
            if len(all_exchanges) >= limit + offset:
                break
            entries = self._read_jsonl(session_file)
            exchanges = [e for e in entries if e.get("_type") == "exchange"]
            all_exchanges.extend(exchanges)

        all_exchanges.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        page = all_exchanges[offset : offset + limit]
        return [
            {
                "timestamp": e.get("timestamp", ""),
                "prompt_preview": str(e.get("prompt", ""))[:200],
                "response_preview": str(e.get("response", ""))[:200],
                "session_id": e.get("metadata", {}).get("session_id", ""),
            }
            for e in page
        ]

    @property
    def stats(self) -> dict:
        """Get session storage stats."""
        hot_files = list(self.hot_dir.glob("*.jsonl"))
        warm_files = list(self.warm_dir.glob("*.json"))
        cold_files = list(self.cold_dir.glob("*.jsonl.gz"))

        hot_size = sum(f.stat().st_size for f in hot_files)
        warm_size = sum(f.stat().st_size for f in list(self.warm_dir.glob("*")))
        cold_size = sum(f.stat().st_size for f in cold_files)

        return {
            "hot_sessions": len(hot_files),
            "warm_sessions": len(warm_files),
            "cold_sessions": len(cold_files),
            "hot_size_mb": round(hot_size / (1024 * 1024), 2),
            "warm_size_mb": round(warm_size / (1024 * 1024), 2),
            "cold_size_mb": round(cold_size / (1024 * 1024), 2),
            "current_session": self._current_session_id,
            "current_entries": self._entry_count,
        }

    # ── Internal helpers ──

    def _count_entries(self, path: Path) -> int:
        """Return exchange count for a JSONL file, using an in-memory cache."""
        key = str(path)
        if key in self._counts_cache:
            return self._counts_cache[key]
        count = 0
        try:
            with open(path) as f:
                for line in f:
                    try:
                        if json.loads(line).get("_type") == "exchange":
                            count += 1
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
        self._counts_cache[key] = count
        return count

    def _read_jsonl(self, path: Path) -> list[dict]:
        entries = []
        try:
            with open(path) as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
        return entries

    def _read_jsonl_gz(self, path: Path) -> list[dict]:
        entries = []
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
        return entries

    @staticmethod
    def _write_gzip(path: Path, entries: list[dict]):
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as gz:
            for entry in entries:
                gz.write(json.dumps(entry) + "\n")
