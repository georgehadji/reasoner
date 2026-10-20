"""
TaggedMemory — lightweight categorized conversation history store.

Organizes history entries by tags (method, preset, outcome) for O(1) lookup.
Backs each tag to a separate JSONL file under base_dir.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class TaggedMemory:
    """Multi-index memory store backed by JSONL files."""

    # A tag file past this is rotated to "<tag>.jsonl.1" (the previous .1 is
    # replaced), which the "*.jsonl" glob no longer reads.
    MAX_FILE_BYTES = 10 * 1024 * 1024

    def __init__(self, base_dir: str | Path = "history") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._store: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        # Loaded on first read. Every run constructs one only to append two
        # entries, and loading re-read every JSONL file in the directory.
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self._load()

    def _load(self) -> None:
        for path in self.base_dir.glob("*.jsonl"):
            tag = path.stem
            entries: list[dict[str, Any]] = []
            try:
                with path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        entries.append(json.loads(line))
            except Exception:
                continue
            self._store[tag] = entries

    def add(self, tag: str, entry: dict[str, Any]) -> None:
        """Append an entry to a tag and persist to disk."""
        import re
        if not tag or not re.match(r'^[a-zA-Z0-9_-]+$', tag):
            raise ValueError(f"Invalid tag name: {tag!r}")
        if self._loaded:
            self._store[tag].append(entry)
        file_path = self.base_dir / f"{tag}.jsonl"
        if file_path.exists() and file_path.stat().st_size > self.MAX_FILE_BYTES:
            file_path.replace(file_path.with_name(f"{tag}.jsonl.1"))
        with file_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def get_by_tag(self, tag: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return the most recent N entries for a tag."""
        self._ensure_loaded()
        return list(self._store.get(tag, [])[-limit:])

    def all_tags(self) -> list[str]:
        self._ensure_loaded()
        return list(self._store.keys())

    def count(self, tag: str | None = None) -> int:
        self._ensure_loaded()
        if tag is not None:
            return len(self._store.get(tag, []))
        return sum(len(v) for v in self._store.values())
