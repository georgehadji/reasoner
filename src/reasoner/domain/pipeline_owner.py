"""Pipeline ownership tracking — shared between API and websocket layers.

Extracted from api/history.py to resolve infrastructure -> api dependency.
"""

from __future__ import annotations

import json
from pathlib import Path

_HISTORY_DIR = Path(__file__).parent / "history"
_HISTORY_DIR.mkdir(exist_ok=True)

_PIPELINE_OWNERS_PATH = _HISTORY_DIR / "pipeline_owners.json"
_MAX_PIPELINE_OWNERS = 50_000


def _get_pipeline_owner(pipeline_id: str) -> str | None:
    """Return the user_id that owns *pipeline_id*, or None if not tracked."""
    if not _PIPELINE_OWNERS_PATH.exists():
        return None
    try:
        mapping = json.loads(_PIPELINE_OWNERS_PATH.read_text(encoding="utf-8"))
        return mapping.get(pipeline_id)
    except Exception:
        return None


def _save_pipeline_owner(pipeline_id: str, user_id: str | None) -> None:
    """Persist ownership mapping for a pipeline run."""
    mapping: dict[str, str | None] = {}
    if _PIPELINE_OWNERS_PATH.exists():
        try:
            mapping = json.loads(_PIPELINE_OWNERS_PATH.read_text(encoding="utf-8"))
        except Exception:
            mapping = {}
    mapping[pipeline_id] = user_id
    if len(mapping) > _MAX_PIPELINE_OWNERS:
        while len(mapping) > _MAX_PIPELINE_OWNERS:
            mapping.pop(next(iter(mapping)))
    _PIPELINE_OWNERS_PATH.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
