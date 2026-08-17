"""Drift guard for ui-next/src/lib/capabilities.generated.ts.

The landing page's capability numbers (reasoning methods, routable models,
provider labs, ...) are generated from live code by
scripts/update_mindmap_meta.py so they cannot silently drift from what the
registry/preset/phase code actually contains — see docs/plans/
homepage-trust-remediation.md, Phase 1. This test regenerates the file's
content in memory and fails if the committed file disagrees, so an editor
who hand-tweaks a number (or forgets to rerun the generator after changing a
preset) finds out in CI, not in a support ticket from an enterprise buyer's
procurement team.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import update_mindmap_meta as mindmap  # noqa: E402


def _strip_volatile(text: str) -> str:
    """Drop fields that legitimately differ between two runs of this test.

    ``generatedAt``/the header date differ same-day vs. next-day. ``testFiles``
    counts ``tests/*.py`` directly — in an actively-developed repo, a test file
    can be added or removed by other work between this generator running at
    commit time and this test running in CI minutes later. That is real,
    expected repo activity, not staleness, so it gets a separate loose sanity
    check below instead of exact-match — the same way you would not assert
    two ``datetime.now()`` calls are equal.
    """
    text = re.sub(r"on \d{4}-\d{2}-\d{2}|generatedAt: '[^']+'", "", text)
    return re.sub(r"testFiles: \d+", "testFiles: N", text)


def test_capabilities_generated_ts_matches_live_counts() -> None:
    committed = mindmap.CAPABILITIES_TS.read_text(encoding="utf-8")

    today = date.today().isoformat()
    fresh = mindmap._render_capabilities_ts(
        today,
        mindmap._count_presets(),
        mindmap._count_methods(),
    )

    assert _strip_volatile(committed) == _strip_volatile(fresh), (
        "ui-next/src/lib/capabilities.generated.ts is stale. Regenerate it with "
        "`python scripts/update_mindmap_meta.py` (or let the post-commit hook do it) "
        "and commit the result — do not hand-edit the numbers."
    )

    match = re.search(r"testFiles: (\d+)", committed)
    assert match, "capabilities.generated.ts is missing a testFiles field"
    live_tests = mindmap._count_test_files()
    assert abs(int(match.group(1)) - live_tests) < 20, (
        f"committed testFiles ({match.group(1)}) is wildly off from the live "
        f"count ({live_tests}) — regenerate if this reflects a real, settled change."
    )


def test_capabilities_excludes_image_generation_models() -> None:
    """directModels must count reasoning-eligible models only.

    _MODEL_WHITELIST also carries image-generation aliases; folding those
    into a number shown next to "reasoning methods" would misrepresent the
    capability, which is exactly the class of claim Phase 0 of the trust
    remediation removed. Guards against a future edit re-merging the counts.
    """
    committed = mindmap.CAPABILITIES_TS.read_text(encoding="utf-8")
    match = re.search(r"directModels: (\d+)", committed)
    assert match, "capabilities.generated.ts is missing a directModels field"

    reasoning_models = mindmap._count_reasoning_models()
    assert int(match.group(1)) == reasoning_models
    assert reasoning_models < mindmap._count_models(), (
        "directModels should be smaller than the raw whitelist size once "
        "image-generation aliases are excluded — if this fails, either the "
        "filter broke or the registry stopped carrying image models."
    )
