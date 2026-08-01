"""
Data directory paths — Core layer, zero outer dependencies.

    @dataclass(frozen=True, slots=True)
    class DataPaths:
        root: Path
        cache: Path
        uploads: Path
        history: Path
        events_db: Path
        errors_db: Path
        feedback_db: Path
        auth_db: Path

        @classmethod
        def from_root(cls, root: Path) -> DataPaths: ...
        def ensure(self) -> None:
            \"\"\"Create every directory. Called once, at the composition root.\"\"\"

Frozen Value Object — not a singleton and not mutable, so test isolation
is straightforward.  Resolved at the composition root and injected into
every consumer via constructor injection.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: Env var controlling the data root.  Read directly rather than through
#: ``core.settings`` so this module keeps zero outer dependencies.
DATA_DIR_ENV = "DATA_DIR"
DEFAULT_DATA_DIR = "./data"


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Every persistent path the application writes to.

    All paths are absolute.  Created by ``from_root()``, which derives
    every path from a single root directory.  The env-var ``DATA_DIR``
    controls the root; default ``./data`` in development and ``/app/data``
    in the container.
    """

    root: Path = field()
    cache: Path = field()
    uploads: Path = field()
    history: Path = field()
    events_db: Path = field()
    errors_db: Path = field()
    feedback_db: Path = field()
    auth_db: Path = field()

    # ── derivation (the only way to construct) ─────────────────────

    @classmethod
    def from_root(cls, root: str | Path) -> DataPaths:
        root = Path(root).resolve()
        return cls(
            root=root,
            cache=root / "cache",
            uploads=root / "uploads",
            history=root / "history",
            events_db=root / "events.db",
            errors_db=root / "errors.db",
            feedback_db=root / "feedback.db",
            auth_db=root / "auth_keys.db",
        )

    # ── lifecycle ──────────────────────────────────────────────────

    def ensure(self) -> None:
        """Create every directory.  Idempotent.  Call once at startup."""
        dirs = {self.cache, self.uploads, self.history}
        for d in sorted(dirs):
            d.mkdir(parents=True, exist_ok=True)
        # Touch DB parent directories (files are created on first use)
        for p in [self.events_db, self.errors_db, self.feedback_db, self.auth_db]:
            p.parent.mkdir(parents=True, exist_ok=True)

    # ── process-wide default ───────────────────────────────────────

    @staticmethod
    def reset_default() -> None:
        """Clear the cached default.  For tests that change ``DATA_DIR``."""
        default_data_paths.cache_clear()

    # ── legacy migration helpers ───────────────────────────────────

    @classmethod
    def detect_legacy(cls) -> dict[str, Path | None]:
        """Return paths to legacy stores keyed by name, or None.

        Reads old ``Path(__file__)``-based locations so the caller can
        migrate data before switching to new paths.
        """
        # These mirror the old Path(__file__) derivations.
        # Package root ≈ src/reasoner → four parent levels up.
        _guess_pkg = Path(__file__).resolve().parent.parent  # reasoner/core/
        _src = _guess_pkg.parent.parent.parent  # repo root

        return {
            "events_db": _guess_pkg.parent / "events.db",
            "errors_db": _src / "errors.db",
            "feedback_db": _src / "feedback.db",
            "cache_dir": _guess_pkg.parent / "cache",
            "uploads_dir": _guess_pkg.parent / "uploads",
            "auth_db": _src / "reasoner" / "auth_keys.db",
        }

    def migrate_from_legacy(self) -> None:
        """Copy (never move) legacy data to new paths.

        Only copies when the new path does not exist and the legacy path
        does — so it is idempotent and safe to run on every startup during
        the transition window.
        """
        import shutil

        legacy = self.detect_legacy()
        mappings: list[tuple[str, Path]] = [
            ("events_db", self.events_db),
            ("errors_db", self.errors_db),
            ("feedback_db", self.feedback_db),
            ("cache_dir", self.cache),
            ("uploads_dir", self.uploads),
            ("auth_db", self.auth_db),
        ]
        for key, new_path in mappings:
            old_path = legacy.get(key)
            if old_path is None or not old_path.exists():
                continue
            if new_path.exists():
                logger.info("New path %s exists; skipping legacy copy from %s", new_path, old_path)
                continue
            if old_path.is_dir():
                shutil.copytree(old_path, new_path)
                logger.warning("Copied legacy directory %s → %s", old_path, new_path)
            else:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_path, new_path)
                logger.warning("Copied legacy file %s → %s", old_path, new_path)


@lru_cache(maxsize=1)
def default_data_paths() -> DataPaths:
    """Return the process-wide ``DataPaths``, derived from ``$DATA_DIR``.

    The composition root (``asgi.py`` / ``main.py``) builds its own
    instance explicitly and injects it; this function is the fallback for
    the many stores that are still constructed without arguments — from
    the CLI, from tests, and from direct imports.

    It exists so that a default-constructed store lands in ``$DATA_DIR``
    rather than inside the installed package.  It is deliberately *not* a
    substitute for constructor injection: an explicit ``db_path`` always
    wins.  Cached so every caller agrees on one root within a process;
    call ``DataPaths.reset_default()`` in tests that repoint ``DATA_DIR``.
    """
    root = os.environ.get(DATA_DIR_ENV) or DEFAULT_DATA_DIR
    paths = DataPaths.from_root(root)
    paths.ensure()
    return paths
