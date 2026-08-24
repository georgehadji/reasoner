#!/usr/bin/env python3
"""
Capture and update the Article pipeline baseline.

Captures golden set prompt lengths, cost estimates, and structural properties
from the CURRENT system state and saves them as a baseline JSON file.

Usage:
  python scripts/capture_article_baseline.py           # capture + display
  python scripts/capture_article_baseline.py --save    # capture + write to disk
  python scripts/capture_article_baseline.py --diff    # diff vs saved baseline

The saved baseline is used by test_article_golden_set.py's baseline-check mode
(ARTICLE_CHECK_BASELINE=1) to detect regressions.

FILES
-----
- Baseline JSON: tests/_data/article_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

# Add project root and src to sys.path so we can import reasoner
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reasoner.domain.pricing import PRICING_DB
from tests.test_article_golden_set import GOLDEN_SET, capture_baseline
from tests.test_article_presets import ARTICLE_PRESET_NAMES

BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tests", "_data", "article_baseline.json"
)


def _collect_cost_baseline() -> dict[str, float]:
    """Estimate cost per preset using token estimates from test_article_presets."""
    from tests.test_article_presets import TestArticlePresetCostBaseline
    estimator = TestArticlePresetCostBaseline()
    costs: dict[str, float] = {}
    for name in ARTICLE_PRESET_NAMES:
        costs[name] = round(estimator._estimate_preset_cost(name), 6)
    return costs


def collect_full_baseline() -> dict:
    """Collect the full baseline: golden set metrics + cost estimates."""
    # Golden set prompt-length baseline
    baseline = capture_baseline()

    # Add cost baseline
    baseline["cost_baseline"] = _collect_cost_baseline()

    # Add metadata
    baseline["meta"]["captured_at"] = datetime.now(UTC).isoformat()
    baseline["meta"]["preset_count"] = len(ARTICLE_PRESET_NAMES)
    baseline["meta"]["pricing_db_entries"] = len(PRICING_DB)

    return baseline


def save_baseline(data: dict, path: str = BASELINE_PATH) -> str:
    """Write baseline JSON to disk."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return path


def load_baseline(path: str = BASELINE_PATH) -> dict | None:
    """Load saved baseline JSON from disk."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def diff_baselines(current: dict, saved: dict | None) -> str:
    """Produce a human-readable diff between current and saved baselines."""
    lines: list[str] = []

    if saved is None:
        return "No saved baseline to diff against."

    # Compare meta
    saved_count = saved.get("meta", {}).get("count", 0)
    current_count = current.get("meta", {}).get("count", 0)
    if saved_count != current_count:
        lines.append(f"  Golden set size: {saved_count} → {current_count}")

    # Compare cost baseline
    saved_costs = saved.get("cost_baseline", {})
    current_costs = current.get("cost_baseline", {})
    for name in sorted(set(list(saved_costs.keys()) + list(current_costs.keys()))):
        sc = saved_costs.get(name, 0)
        cc = current_costs.get(name, 0)
        if abs(sc - cc) > 0.001:
            pct = ((cc - sc) / sc * 100) if sc > 0 else float("inf")
            lines.append(f"  Cost [{name}]: ${sc:.6f} → ${cc:.6f} ({pct:+.1f}%)")

    # Compare prompt lengths per golden set entry
    saved_entries = saved.get("entries", {})
    current_entries = current.get("entries", {})
    for tc_id in sorted(set(list(saved_entries.keys()) + list(current_entries.keys()))):
        se = saved_entries.get(tc_id, {})
        ce = current_entries.get(tc_id, {})
        saved_lengths = se.get("prompt_lengths", {})
        current_lengths = ce.get("prompt_lengths", {})
        for pn in sorted(set(list(saved_lengths.keys()) + list(current_lengths.keys()))):
            sl = saved_lengths.get(pn, 0)
            cl = current_lengths.get(pn, 0)
            if sl > 0 and cl > 0:
                ratio = cl / sl
                if ratio < 0.8 or ratio > 1.2:
                    pct = ((cl - sl) / sl * 100)
                    lines.append(
                        f"  Prompt [{tc_id}/{pn}]: {sl} → {cl} chars ({pct:+.1f}%)"
                    )

    if not lines:
        return "No significant changes detected."

    return "Changes detected:\n" + "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Article pipeline baseline tool")
    parser.add_argument("--save", action="store_true", help="Save baseline to disk")
    parser.add_argument("--diff", action="store_true", help="Diff current vs saved baseline")
    parser.add_argument("--path", default=BASELINE_PATH, help="Baseline JSON path")
    args = parser.parse_args()

    print(f"Collecting baseline from {len(GOLDEN_SET)} golden set entries...")
    baseline = collect_full_baseline()

    if args.diff:
        saved = load_baseline(args.path)
        print(diff_baselines(baseline, saved))
        return

    print(f"\nGolden set: {len(GOLDEN_SET)} entries")
    print("Cost baseline:")
    for name, cost in baseline.get("cost_baseline", {}).items():
        print(f"  {name}: ${cost:.6f}")
    print(f"Pricing DB: {len(PRICING_DB)} entries")

    # Print prompt length stats
    prompt_lengths = []
    for tc_id, entry in baseline.get("entries", {}).items():
        for pn, pl in entry.get("prompt_lengths", {}).items():
            if pl > 0:
                prompt_lengths.append((tc_id, pn, pl))

    if prompt_lengths:
        avg_len = sum(pl for _, _, pl in prompt_lengths) / len(prompt_lengths)
        max_len = max(pl for _, _, pl in prompt_lengths)
        min_len = min(pl for _, _, pl in prompt_lengths)
        print(f"\nPrompt lengths: avg={avg_len:.0f}, min={min_len}, max={max_len} chars")
        print(f"  (across {len(prompt_lengths)} prompt x golden-set pairs)")

    if args.save:
        path = save_baseline(baseline, args.path)
        print(f"\nSaved baseline to {path}")
    else:
        print(f"\nDry run — use --save to persist baseline to {args.path}")


if __name__ == "__main__":
    main()
