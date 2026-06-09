"""Export recent telemetry to healing_context.json for static healing scripts.

Called by run_healing.py at the start of the healing pipeline.
If TelemetryStore is unavailable or has no data, healing continues unaffected.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Written to the Reasoner project root (two levels up from src/reasoner/healing/)
CONTEXT_PATH = Path(__file__).resolve().parent.parent.parent.parent / "healing_context.json"


async def _build_context() -> dict[str, Any]:
    """Query TelemetryStore and aggregate by preset."""
    from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store
    store = get_telemetry_store()
    recent = await store.query_recent(limit=200)
    if not recent:
        return {"status": "no_runs", "presets": {}}

    presets: dict[str, Any] = {}
    for row in recent:
        preset = row["preset"]
        if preset not in presets:
            presets[preset] = {
                "run_count": 0, "total_cost_usd": 0.0, "total_fallbacks": 0,
            }
        presets[preset]["run_count"] += 1
        presets[preset]["total_cost_usd"] += row.get("total_cost_usd", 0.0)
        presets[preset]["total_fallbacks"] += row.get("fallback_count", 0)

    top_presets = sorted(presets, key=lambda p: presets[p]["run_count"], reverse=True)[:5]
    stats = {}
    for preset in top_presets:
        try:
            stats[preset] = await store.get_preset_stats(preset)
        except Exception as exc:
            logger.debug("Stats failed for %s: %s", preset, exc)

    return {
        "status": "ok",
        "run_count": len(recent),
        "presets": presets,
        "preset_stats": stats,
    }


def export_healing_context() -> bool:
    """Write healing_context.json. Returns True on success."""
    try:
        context = asyncio.run(_build_context())
        CONTEXT_PATH.write_text(json.dumps(context, indent=2), encoding="utf-8")
        logger.info(
            "Healing context written to %s (%d runs)",
            CONTEXT_PATH, context.get("run_count", 0),
        )
        return True
    except Exception as exc:
        logger.warning("Healing context export failed (non-fatal): %s", exc)
        return False
