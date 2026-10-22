"""Crash-safe and multi-writer-safe JSON files on a local volume.

Lowest layer (.importlinter contract 1): imports nothing from ``reasoner``.
That is why ``read_json_or_quarantine`` returns a flag instead of reporting
the corruption itself; the caller reports it with ``core.degrade.degraded()``.

docs/plans/audit-remediation-2-2026-10-20.md PER-8 and PER-10: the upload
hash index and the Neuro L2 index were whole-file read-modify-writes with no
lock and no atomic rename, so concurrent writers lost entries and a crash
mid-write left a half file that the next load read as empty and the next
save then made permanent.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so a reader sees the old or the new file, never half.

    The temp name is unique per writer (pid + ns), so two writers never share
    a temp file; the last ``os.replace`` wins.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """Hold an exclusive advisory lock for a read-modify-write of ``path``.

    The lock is a sibling ``.lock`` file, so it works across processes and
    across threads (each call opens its own handle). Advisory only: every
    writer of ``path`` must take it.
    """
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    # LK_LOCK itself retries for ~10s, then raises; keep waiting.
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def read_json_or_quarantine(path: Path, default: Any) -> tuple[Any, bool]:
    """Load JSON from ``path``; on a parse error move the file aside.

    Returns ``(value, quarantined)``. A missing file is ``(default, False)``.
    An unparsable file is renamed to ``*.corrupt-{ts}`` and returns
    ``(default, True)``, so the next save cannot overwrite the only copy of
    the data with an empty file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default, False
    try:
        return json.loads(text), False
    except ValueError:
        path.replace(path.with_name(f"{path.name}.corrupt-{time.time_ns()}"))
        return default, True
