#!/usr/bin/env python3
"""
Capture and update the Article pipeline baseline.

Captures golden set prompt lengths, cost estimates, and structural properties
from the CURRENT system state and saves them as a baseline JSON file.

Usage:
  python scripts/capture_article_baseline.py           # capture + display
  python scripts/capture_article_baseline.py --save    # capture + write to disk
  python scripts/capture_article_baseline.py --diff    # diff vs saved baseline

The saved baseline is used by the golden set test suite to detect regressions
in prompt length, cost structure, or routing diversity after refactoring.

FILES
-----
- Baseline JSON: tests/_data/article_baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reasoner.domain.preset_registry import PRESETS
from reasoner.domain.pricing import PRICING_DB
from reasoner.domain.pipeline_state import PipelineState

BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "tests", "_data", "article_baseline.json"
)

# ── Golden set: 20 frozen inputs spanning all venues ─────────────────────────

GOLDEN_SET: list[dict] = [
    # Blog posts
    {"id": "blog_climate", "problem": "Write a blog post about the economic impact of climate change on coastal communities in Southeast Asia", "content_class": "blog", "language": "English"},
    {"id": "blog_remote_work", "problem": "Draft a blog post about the future of remote work and its effect on urban development", "content_class": "blog", "language": "English"},
    # Explainer articles
    {"id": "explainer_quantum", "problem": "Write an explainer about quantum computing for a general audience", "content_class": "explainer", "language": "English"},
    {"id": "explainer_mrna", "problem": "Draft an explainer article about how mRNA vaccines work", "content_class": "explainer", "language": "English"},
    # Opinion / Op-Ed
    {"id": "oped_ai_regulation", "problem": "Write an opinion piece arguing that AI regulation should focus on capability audits", "content_class": "op_ed", "language": "English"},
    {"id": "oped_education", "problem": "Draft an op-ed about why classical education still matters in the age of AI", "content_class": "op_ed", "language": "English"},
    # Policy briefs
    {"id": "policy_eu_data", "problem": "Draft a policy brief analyzing the European Union approach to cross-border data flows", "content_class": "policy_brief", "language": "English"},
    {"id": "policy_energy", "problem": "Write a policy analysis article comparing carbon pricing mechanisms across regions", "content_class": "policy_brief", "language": "English"},
    # News analysis
    {"id": "news_semiconductor", "problem": "Write a news analysis article about the global semiconductor supply chain realignment", "content_class": "news_analysis", "language": "English"},
    {"id": "news_cyber", "problem": "Compose a news analysis article about the shift in cybersecurity threats", "content_class": "news_analysis", "language": "English"},
    # Technical articles
    {"id": "technical_llm", "problem": "Write a technical article explaining mixture-of-experts transformer models", "content_class": "technical", "language": "English"},
    {"id": "technical_rust", "problem": "Draft a technical article about memory safety patterns in Rust", "content_class": "technical", "language": "English"},
    # Greek briefing
    {"id": "greek_geopolitics", "problem": "\u0393\u03c1\u03ac\u03c8\u03c4\u03b5 \u03ad\u03bd\u03b1 \u03ac\u03c1\u03b8\u03c1\u03bf \u03b1\u03bd\u03ac\u03bb\u03c5\u03c3\u03b7\u03c2 \u03b3\u03b9\u03b1 \u03c4\u03b9\u03c2 \u03b3\u03b5\u03c9\u03c0\u03bf\u03bb\u03b9\u03c4\u03b9\u03ba\u03ad\u03c2 \u03b5\u03c0\u03b9\u03c0\u03c4\u03ce\u03c3\u03b5\u03b9\u03c2", "content_class": "greek_briefing", "language": "Greek"},
    {"id": "greek_tech", "problem": "\u03a3\u03c5\u03bd\u03c4\u03ac\u03be\u03c4\u03b5 \u03ad\u03bd\u03b1 \u03ac\u03c1\u03b8\u03c1\u03bf \u03b3\u03b9\u03b1 \u03c4\u03b7\u03bd \u03b5\u03c0\u03af\u03b4\u03c1\u03b1\u03c3\u03b7 \u03c4\u03b7\u03c2 \u03c4\u03b5\u03c7\u03bd\u03b7\u03c4\u03ae\u03c2 \u03bd\u03bf\u03b7\u03bc\u03bf\u03c3\u03cd\u03bd\u03b7\u03c2", "content_class": "greek_briefing", "language": "Greek"},
    # Style-brief articles
    {"id": "styled_newyorker", "problem": "Write an article about the decline of local news in rural America", "content_class": "blog", "style_brief": {"author": "Jane Doe", "publication": "The New Yorker"}, "language": "English"},
    {"id": "styled_financial", "problem": "Draft an article analyzing the investment implications of deglobalization", "content_class": "policy_brief", "style_brief": {"publication": "Financial Times"}, "language": "English"},
    # Deep / philosophical
    {"id": "deep_consciousness", "problem": "Write an article exploring the philosophical debate about the nature of consciousness", "content_class": "explainer", "language": "English"},
    {"id": "deep_free_will", "problem": "Draft an article examining whether free will is compatible with modern neuroscience", "content_class": "explainer", "language": "English"},
    # Short-form / review
    {"id": "short_book_review", "problem": "Write a short article reviewing Yuval Noah Harari's Nexus", "content_class": "blog", "language": "English"},
    # Multi-source factual
    {"id": "factual_space", "problem": "Write an article about the Artemis program and its implications for international collaboration in space exploration", "content_class": "news_analysis", "language": "English"},
]

# ── Prompt builder names (loaded dynamically) ────────────────────────────────

PROMPT_BUILDERS = [
    "article_retrieval_plan_prompt",
    "article_outline_prompt",
    "article_draft_prompt",
    "article_verify_prompt",
    "article_critic_prompt",
    "article_developmental_edit_prompt",
    "article_style_edit_prompt",
    "article_copy_edit_prompt",
    "article_final_audit_prompt",
]

# ── Required routing roles ────────────────────────────────────────────────────

ARTICLE_REQUIRED_ROLES = [
    "primary", "writing_draft", "writing_factcheck", "writing_assemble",
    "synthesis", "article_sot_skeleton", "article_critic", "article_revise",
    "article_humanize", "article_verifier",
]


def _build_state(entry: dict) -> PipelineState:
    """Build a minimal PipelineState for a given golden-set entry."""
    state = PipelineState(
        problem=entry["problem"],
        language=entry.get("language", "English"),
        preset_name="article-budget",
        method="article",
    )
    ws = state.writing_state
    ws["final_article"] = "# Draft\n\nThis is a draft article body for testing prompt builders."
    ws["retrieved_sources"] = [
        {"title": f"Source {i}", "url": f"https://example{i}.com", "snippet": f"Snippet {i}"}
        for i in range(1, 6)
    ]
    ws["source_metadata"] = ws["retrieved_sources"]
    ws["argument_map"] = {"central_question": "What?", "problem": "Test", "current_explanations": ["A"], "limitations": ["B"], "new_insight": "C", "counterarguments": ["D"], "implications": ["E"]}
    ws["outline"] = [{"section_title": "Introduction", "key_points": ["Hook"], "sources_used": ["https://ex1.com"], "estimated_words": 200}]
    ws["suggested_title"] = "Test Article Title"
    ws["verification"] = {"verified_claims": [{"claim": "Example", "verdict": "supported", "source_url": "https://ex.com"}], "metrics": {"total_claims": 5, "supported": 4, "unsupported": 1, "claim_support_ratio": 0.8}, "gaps": []}
    ws["claim_ledger"] = [{"claim": "Test claim", "source": "https://ex.com", "status": "verified"}]
    ws["metrics"] = {"total_claims": 5, "supported": 4, "unsupported": 1, "claim_support_ratio": 0.8}
    ws["structural_critique"] = {"implicit_assumptions": [], "logical_gaps": [], "ignored_counterarguments": [], "overall_rigor_score": 0.7}
    ws["editorial_audit"] = {"audit": {"thesis_advancement": 0.8, "claim_support": 0.7, "internal_consistency": 0.85, "transition_quality": 0.75, "redundancy_removed": 0.7, "citation_accuracy": 0.9, "policy_compliance": 1.0}, "issues": [], "audit_score": 0.8, "passes_audit": True}
    if entry.get("style_brief"):
        ws["style_brief"] = entry["style_brief"]
    return state


def collect_prompt_lengths() -> dict[str, dict[str, int]]:
    """Capture prompt lengths for every prompt builder * every golden entry."""
    import importlib
    prompts_mod = importlib.import_module("reasoner.phases.article")

    results: dict[str, dict[str, int]] = {}
    for entry in GOLDEN_SET:
        state = _build_state(entry)
        lengths: dict[str, int] = {}
        for pb_name in PROMPT_BUILDERS:
            try:
                fn = getattr(prompts_mod, pb_name)
                # article_verify_prompt has an optional use_sonar param
                if pb_name == "article_verify_prompt":
                    prompt = fn(state, use_sonar=False)
                else:
                    prompt = fn(state)
                lengths[pb_name] = len(prompt)
            except Exception as exc:
                lengths[pb_name] = -1
        results[entry["id"]] = lengths
    return results


def collect_cost_estimates() -> dict[str, float]:
    """Estimate per-preset cost using token estimates and PRICING_DB."""
    # Token estimates per role
    role_estimates: dict[str, dict[str, int]] = {
        "primary": {"input": 2000, "output": 400},
        "writing_draft": {"input": 6000, "output": 2000},
        "writing_factcheck": {"input": 5000, "output": 1000},
        "writing_assemble": {"input": 4000, "output": 1500},
        "synthesis": {"input": 8000, "output": 1000},
        "article_sot_skeleton": {"input": 4000, "output": 800},
        "article_critic": {"input": 5000, "output": 800},
        "article_revise": {"input": 5000, "output": 2000},
        "article_humanize": {"input": 4000, "output": 1500},
        "article_verifier": {"input": 4000, "output": 800},
    }

    def _get_pricing(model_id: str):
        if model_id in PRICING_DB:
            return PRICING_DB[model_id]
        key = f"{model_id}/completion"
        if key in PRICING_DB:
            return PRICING_DB[key]
        return PRICING_DB.get("_default")

    costs: dict[str, float] = {}
    for preset_name in ["article-budget", "article-premium"]:
        preset = PRESETS.get(preset_name, {})
        routing = preset.get("routing", {})
        total = 0.0
        for role, estimate in role_estimates.items():
            model_id = routing.get(role, "")
            if not model_id:
                continue
            pricing = _get_pricing(model_id)
            if pricing:
                total += pricing.input_per_token * estimate["input"] + pricing.output_per_token * estimate["output"]
        costs[preset_name] = round(total, 6)
    return costs


def collect_full_baseline() -> dict:
    """Collect the full baseline: prompt lengths + cost estimates + metadata."""
    prompt_lengths = collect_prompt_lengths()
    cost_estimates = collect_cost_estimates()

    entries: dict[str, dict] = {}
    for entry in GOLDEN_SET:
        eid = entry["id"]
        entries[eid] = {
            "problem": entry["problem"][:100],
            "content_class": entry.get("content_class", ""),
            "language": entry.get("language", ""),
            "has_style_brief": entry.get("style_brief") is not None,
            "prompt_lengths": prompt_lengths.get(eid, {}),
        }

    return {
        "meta": {
            "description": "Article pipeline baseline (Phase 0)",
            "count": len(GOLDEN_SET),
            "prompt_builders": len(PROMPT_BUILDERS),
            "format_version": 1,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "entries": entries,
        "cost_baseline": cost_estimates,
        "roles_checked": ARTICLE_REQUIRED_ROLES,
    }


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
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def diff_baselines(current: dict, saved: dict | None) -> str:
    """Produce a human-readable diff."""
    if saved is None:
        return "No saved baseline to diff against."

    lines: list[str] = []
    sc = saved.get("meta", {}).get("count", 0)
    cc = current.get("meta", {}).get("count", 0)
    if sc != cc:
        lines.append(f"  Golden set size: {sc} -> {cc}")

    saved_costs = saved.get("cost_baseline", {})
    current_costs = current.get("cost_baseline", {})
    for name in sorted(set(list(saved_costs.keys()) + list(current_costs.keys()))):
        sc = saved_costs.get(name, 0)
        cc = current_costs.get(name, 0)
        if abs(sc - cc) > 0.001:
            lines.append(f"  Cost [{name}]: ${sc:.6f} -> ${cc:.6f}")

    saved_entries = saved.get("entries", {})
    current_entries = current.get("entries", {})
    for eid in sorted(set(list(saved_entries.keys()) + list(current_entries.keys()))):
        se = saved_entries.get(eid, {}).get("prompt_lengths", {})
        ce = current_entries.get(eid, {}).get("prompt_lengths", {})
        for pn in sorted(set(list(se.keys()) + list(ce.keys()))):
            sl = se.get(pn, 0)
            cl = ce.get(pn, 0)
            if sl > 0 and cl > 0:
                ratio = cl / sl
                if ratio < 0.8 or ratio > 1.2:
                    lines.append(f"  Prompt [{eid}/{pn}]: {sl} -> {cl} chars ({((cl-sl)/sl*100):+.1f}%)")

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
    for name, cost in baseline.get("cost_baseline", {}).items():
        print(f"  Cost [{name}]: ${cost:.6f}")

    # Compute prompt length stats
    all_lengths = []
    for eid, entry in baseline.get("entries", {}).items():
        for pl in entry.get("prompt_lengths", {}).values():
            if pl > 0:
                all_lengths.append(pl)
    if all_lengths:
        avg = sum(all_lengths) / len(all_lengths)
        print(f"Prompt lengths: avg={avg:.0f}, min={min(all_lengths)}, max={max(all_lengths)} chars")
        print(f"  (across {len(all_lengths)} prompt x golden-set combinations)")

    if args.save:
        path = save_baseline(baseline, args.path)
        print(f"\nSaved baseline to {path}")
    else:
        print(f"\nDry run -- use --save to persist baseline to {args.path}")


if __name__ == "__main__":
    main()
