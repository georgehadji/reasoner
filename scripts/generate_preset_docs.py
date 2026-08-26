"""Regenerate the two preset reference docs from `domain/preset_registry.py`.

Both files are pure projections of the registry, and both said so in their own
headers — but nothing produced them, so they rotted. `preset-phase-model-matrix.md`
had carried a "STALE — regenerate before relying on this file" banner since
2026-08-20 with no way to act on it.

    python scripts/generate_preset_docs.py            # rewrite both docs
    python scripts/generate_preset_docs.py --check    # exit 1 if stale (CI)

Everything except `_METHOD_PURPOSES` is derived: routing comes from the preset
registry, served models from the model registry, bloc/price/context from the ACR
capability registry (same catalogue the ACR coverage tests assert against), and
labs from the evolution harness guard. Fallbacks mirror `ProviderRouter._resolve_fallback`.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from reasoner.application.services.harness_guard import get_model_lab  # noqa: E402
from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.capability_registry import CapabilityRegistry  # noqa: E402
from reasoner.infrastructure.llm.registry import resolved_model_of  # noqa: E402

DOC_METHODS = ROOT / "docs" / "methods_and_presets.md"
DOC_MATRIX = ROOT / "docs" / "preset-phase-model-matrix.md"

# The only non-derivable content in either doc: a one-line gloss per method.
# Add a line here when a method is added; the generator fails loudly if one is missing.
_METHOD_PURPOSES: dict[str, str] = {
    "analogical": "Cross-domain analogy mapping and transfer",
    "article": "10-phase publication-grade editorial pipeline with voice-consistent models",
    "bayesian": "Prior→likelihood→posterior→sensitivity reasoning",
    "brainstorming": "Verbalized Sampling: multi-round divergent + convergent ideation",
    "coding": "5-phase production code: spec→generate→review→test→assemble",
    "cove": "Chain-of-Verification: draft→verify→answer→revise",
    "cross-language": "DeepL-powered cross-language reasoning",
    "debate": "Two-model adversarial debate with judging",
    "delphi": "Multi-round expert consensus with convergence tracking",
    "dialectical": "Hegelian thesis→antithesis→synthesis",
    "image-gen": "Image generation and prompt engineering",
    "iterative-critique": "Adversarial generator-critic convergence loop",
    "jury": "Multi-generator panel scored by independent critics",
    "multi-perspective": "Default: multi-perspective generation across diverse labs",
    "pot": "Program-of-Thought: executable code as intermediate reasoning",
    "pre_mortem": "Prospective hindsight failure analysis",
    "research": "Web-grounded deep research with iterative search",
    "scientific": "Hypothesis→falsification→evidence→synthesis",
    "self_discover": "Dynamic selection and composition of reasoning modules",
    "socratic": "Elenchus questioning to expose hidden assumptions",
    "sot": "Skeleton-of-Thought: skeleton→parallel solve→assemble",
    "subagent": "Per-subagent routing with dedicated cross-lab models",
    "tot": "Tree-of-Thoughts: tree search with backtracking",
    "writing": "Research-backed writing via CoVE+SoT+Pre-Mortem",
}


def _capabilities() -> dict:
    """ACR profiles, keyed by alias. Isolated file — never touch ~/.reasoner."""
    path = os.path.join(tempfile.mkdtemp(prefix="preset-docs-"), "capability_profiles.json")
    return CapabilityRegistry(profiles_path=path).get_all_profiles()


PROFILES = _capabilities()


def _served(alias: str) -> str:
    return resolved_model_of(alias) or alias


def _bloc(alias: str) -> str:
    p = PROFILES.get(alias)
    return (p.constraints.bloc if p else "") or "?"


def _price_ctx(alias: str) -> str:
    p = PROFILES.get(alias)
    if p is None:
        return "unknown"
    c = p.constraints
    # Catalogue prices are per-token; the doc has always shown per-million.
    inp = round(c.cost_per_1k_input_usd * 1000, 4)
    out = round(c.cost_per_1k_output_usd * 1000, 4)
    ctx = f"{c.max_context_tokens // 1000}K" if c.max_context_tokens else "?"
    return f"${inp:g}/${out:g} {ctx}"


def _roles(cfg: dict) -> list[tuple[str, str]]:
    """(role, alias) pairs in registry order, primary first."""
    return [("primary", cfg["primary_id"]), *(cfg.get("routing") or {}).items()]


def _fallback(cfg: dict, role: str, alias: str) -> str | None:
    """Mirror of `ProviderRouter._resolve_fallback`, in alias space.

    Precedence explicit > primary > none, dropping any candidate that resolves to
    the same *served* model as the assigned one — re-issuing an identical request
    against an endpoint that just failed is not a fallback.
    """
    primary = cfg["primary_id"]
    fallbacks = cfg.get("fallback_routing") or {}
    explicit = fallbacks.get(role)
    if explicit is None and alias == primary:
        explicit = fallbacks.get("primary")

    candidates = [c for c in (explicit, primary) if c is not None and c != alias]
    assigned_served = _served(alias)
    return next((c for c in candidates if _served(c) != assigned_served), None)


def render_methods_doc() -> str:
    methods = sorted({cfg["method"] for cfg in PRESETS.values()})
    missing = [m for m in methods if m not in _METHOD_PURPOSES]
    if missing:
        raise SystemExit(f"add a _METHOD_PURPOSES line for: {missing}")

    out = [
        "# Reasoner — Methods & Presets Reference",
        "",
        f"**Total presets:** {len(PRESETS)}  ",
        f"**Total methods:** {len(methods)}  ",
        f"**Last updated:** {date.today().isoformat()}  ",
        "**Generated by:** `python scripts/generate_preset_docs.py` — do not edit by hand.",
        "",
        "---",
        "",
        "## Methods",
        "",
        "| # | Method | Presets | Purpose |",
        "|---|--------|---------|---------|",
    ]
    for i, method in enumerate(methods, 1):
        n = sum(1 for c in PRESETS.values() if c["method"] == method)
        out.append(f"| {i} | `{method}` | {n} | {_METHOD_PURPOSES[method]} |")

    out += ["", "---", "", "## Presets by Method", ""]
    for method in methods:
        out += [f"### {method}", ""]
        for pid in sorted(p for p, c in PRESETS.items() if c["method"] == method):
            cfg = PRESETS[pid]
            roles = _roles(cfg)
            out += [
                f"#### `{pid}` — {len(roles)} roles",
                "| Role | Key | Model | Lab |",
                "|------|-----|-------|-----|",
            ]
            for role, alias in roles:
                out.append(f"| {role} | `{alias}` | {_served(alias)} | {get_model_lab(alias)} |")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_matrix_doc() -> str:
    rows: list[tuple[str, dict, list[tuple[str, str, str | None]]]] = []
    orphans = total = 0
    for pid in sorted(PRESETS):
        cfg = PRESETS[pid]
        entries = []
        # primary_id first, remaining roles alphabetical — stable across edits.
        ordered = [("primary_id", cfg["primary_id"])] + sorted((cfg.get("routing") or {}).items())
        for role, alias in ordered:
            fb = _fallback(cfg, "primary" if role == "primary_id" else role, alias)
            entries.append((role, alias, fb))
            total += 1
            orphans += fb is None
        rows.append((pid, cfg, entries))

    out = [
        "# Preset -> Phase -> Model Matrix",
        "",
        "Generated by `python scripts/generate_preset_docs.py` from"
        " `domain/preset_registry.py` — do not edit by hand.",
        f"Regenerated {date.today().isoformat()}.",
        "",
        "`resolved` = the actually-served model. Several aliases route cross-vendor"
        " (e.g. `gemini-pro` -> Anthropic, `gemini-flash-lite` -> Qwen), so the alias"
        " is not a reliable guide to which lab answers.",
        "",
        "**Fallback** mirrors `ProviderRouter._resolve_fallback` precedence: explicit"
        " `fallback_routing[role]` > `fallback_routing['primary']` (only when the role"
        " already uses the primary model) > the primary model itself. Candidates"
        " resolving to the *same served model* as the assigned one are dropped, so"
        " **none** means a failure on that role has nowhere to go.",
        "",
        f"Across all {len(PRESETS)} presets: **{orphans} of {total} role slots have"
        " no usable fallback.**",
        "",
    ]
    for pid, cfg, entries in rows:
        out += [
            f"## `{pid}`",
            "",
            f"method `{cfg['method']}` | tags: {', '.join(cfg.get('tags') or []) or 'none'}",
            "",
            "| role | model | bloc | resolved | price/ctx | fallback |",
            "|---|---|---|---|---|---|",
        ]
        for role, alias, fb in entries:
            fb_cell = f"`{fb}`" if fb else "**none**"
            out.append(
                f"| `{role}` | `{alias}` | {_bloc(alias)} | `{_served(alias)}` "
                f"| {_price_ctx(alias)} | {fb_cell} |"
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if a doc is stale")
    args = ap.parse_args()

    stale = False
    for path, text in ((DOC_METHODS, render_methods_doc()), (DOC_MATRIX, render_matrix_doc())):
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        # The date line moves every day; comparing it would make --check useless.
        if _undated(current) == _undated(text):
            print(f"up to date: {path.relative_to(ROOT)}")
            continue
        stale = True
        if args.check:
            print(f"STALE: {path.relative_to(ROOT)}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)} ({len(text.splitlines())} lines)")

    if args.check and stale:
        print("\nrun: python scripts/generate_preset_docs.py")
        return 1
    return 0


def _undated(text: str) -> str:
    drop = ("**Last updated:**", "Regenerated ")
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith(drop))


if __name__ == "__main__":
    raise SystemExit(main())
