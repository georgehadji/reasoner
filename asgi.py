"""ASGI entry-point. Run with: uvicorn asgi:app --host 0.0.0.0 --port 8003"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

# ── Composition root ─────────────────────────────────────────────
# Bootstrap data paths before any module-level code runs.
# This ensures stores write to the configured DATA_DIR, not inside
# the package tree.
from reasoner.core.paths import DataPaths

data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
paths = DataPaths.from_root(data_dir)
paths.ensure()
paths.migrate_from_legacy()

# Inject paths into module-level singletons
from reasoner.api.cache import configure_cache_dir
configure_cache_dir(paths.cache)

from reasoner.infrastructure.uploader import configure_upload_dir
configure_upload_dir(paths.uploads)

# ── App import (safe now that paths are configured) ──────────────
from reasoner.api import app

# Make paths accessible to the app for dependency injection
app.state.data_paths = paths
