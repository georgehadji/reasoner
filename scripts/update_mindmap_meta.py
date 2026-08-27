"""
Patch dynamic metadata in architecture/codebase docs after each commit.

Targets:
  - ARCHITECTURE_MINDMAP.md  (root)
  - docs/CODEBASE_MINDMAP.md
  - docs/CODEMAPS/*.md       (<!-- Generated: ... --> headers)

Updates: Last Updated date, Python source file count, model count,
preset count, reasoning method count — all derived from live code.
Leaves all prose untouched.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_MINDMAP = ROOT / "ARCHITECTURE_MINDMAP.md"
CODEBASE_MINDMAP = ROOT / "docs" / "CODEBASE_MINDMAP.md"
CODEMAPS_DIR = ROOT / "docs" / "CODEMAPS"


# ── Live counts ──────────────────────────────────────────────────────────────

def _count_py_files() -> int:
    src = ROOT / "src" / "reasoner"
    return len(list(src.rglob("*.py"))) if src.exists() else 0


def _count_models() -> int:
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.infrastructure.llm.registry")
        whitelist = getattr(mod, "_MODEL_WHITELIST", None)
        return len(whitelist) if whitelist else 0
    except Exception:
        return 0


def _count_presets() -> int:
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.presets")
        presets = getattr(mod, "PRESETS", None)
        return len(presets) if presets else 0
    except Exception:
        return 0


def _count_methods() -> int:
    phases_dir = ROOT / "src" / "reasoner" / "phases"
    if not phases_dir.exists():
        return 0
    return len([
        f for f in phases_dir.glob("*.py")
        if not f.stem.startswith("_") and f.stem != "__init__"
    ])


def _count_reasoning_models() -> int:
    """Direct-registry models usable for text reasoning.

    ``_MODEL_WHITELIST`` also carries image-generation aliases (marked
    ``extra_body.include_images``), which are a real capability but a
    different one — folding them into a "models" count next to "reasoning
    methods" on the marketing site would be as misleading as the overclaims
    this generator exists to prevent.
    """
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.infrastructure.llm.registry")
        whitelist = getattr(mod, "_MODEL_WHITELIST", None) or {}
        return sum(
            1 for cfg in whitelist.values()
            if not (isinstance(cfg, dict) and cfg.get("extra_body", {}).get("include_images"))
        )
    except Exception:
        return 0


def _count_routable_models() -> int:
    """Models reachable via OpenRouter — the live catalogue snapshot, not a guess."""
    catalogue = ROOT / "src" / "reasoner" / "domain" / "openrouter_models.json"
    if not catalogue.exists():
        return 0
    try:
        import json
        data = json.loads(catalogue.read_text(encoding="utf-8"))
        return len(data.get("data", []))
    except Exception:
        return 0


def _fallback_provider_registry() -> dict:
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.infrastructure.llm.providers.direct")
        return getattr(mod, "_FALLBACK_PROVIDER_REGISTRY", {}) or {}
    except Exception:
        return {}


def _count_provider_adapters() -> int:
    return len(_fallback_provider_registry())


# ── Sycophancy controls ──────────────────────────────────────────────────────
# Each detector inspects the code a landing-page claim is about and returns
# True only when the mechanism is actually present, at its use site rather
# than its definition — the same contract as the counts above: marketing copy
# cannot state a control the code does not implement. See
# docs/plans/sycophancy-mitigation.md workstream W10.

def _reward_signal_excludes_user_rating() -> bool:
    """W5: the online learner's reward has no approval-shaped input, and is wired to check it."""
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        guard = importlib.import_module("reasoner.core.learning_guard")
        telemetry_mod = importlib.import_module("reasoner.domain.telemetry")
        fields = frozenset(telemetry_mod.LLMCallTelemetry.__dataclass_fields__)
        ok, _ = guard.check_reward_signal_purity(fields)
        if not ok:
            return False
        learner_src = (
            ROOT / "src" / "reasoner" / "infrastructure" / "learning" / "online_learner.py"
        ).read_text(encoding="utf-8")
        return "check_reward_signal_purity(" in learner_src
    except Exception:
        return False


def _destructive_in_default_perspectives() -> bool:
    """W... (existing property): DEFAULT_PERSPECTIVES always includes 'destructive'."""
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.core.perspectives")
        names = {p.name for p in getattr(mod, "DEFAULT_PERSPECTIVES", [])}
        return "destructive" in names
    except Exception:
        return False


def _critique_prompt_has_confidence_penalty() -> bool:
    """critique_prompt() penalises confident-but-unsupported claims."""
    path = ROOT / "src" / "reasoner" / "phases" / "multi_perspective.py"
    if not path.exists():
        return False
    return "confidence_vs_accuracy_penalty" in path.read_text(encoding="utf-8")


def _no_preset_varies_by_stance() -> bool:
    """No preset config carries a tone/stance/personality field.

    A structural check against the field names PipelinePreset actually has,
    not a claim about runtime behaviour that would need every preset executed
    to verify.
    """
    banned = {"tone", "stance", "personality", "style", "warmth"}
    try:
        import importlib
        sys.path.insert(0, str(ROOT / "src"))
        mod = importlib.import_module("reasoner.presets")
        presets = getattr(mod, "PRESETS", None) or {}
        for cfg in presets.values():
            keys = set(vars(cfg).keys()) if hasattr(cfg, "__dict__") else set(cfg.keys())
            if keys & banned:
                return False
        return True
    except Exception:
        return False


def _direct_prompts_carry_epistemic_rules() -> bool:
    """W1: DIRECT-path system prompts treat a stated conclusion as a claim, not a premise."""
    path = ROOT / "src" / "reasoner" / "phases" / "direct.py"
    if not path.exists():
        return False
    return "_DIRECT_EPISTEMIC_RULES" in path.read_text(encoding="utf-8")


def _premise_audit_enabled() -> bool:
    """W2: Phase-1 assumptions carry origin/load_bearing and a parser enforces the VERIFIED rule."""
    core_types = ROOT / "src" / "reasoner" / "domain" / "core_types.py"
    parsing = ROOT / "src" / "reasoner" / "core" / "parsing.py"
    if not (core_types.exists() and parsing.exists()):
        return False
    return (
        "load_bearing: bool" in core_types.read_text(encoding="utf-8")
        and "_parse_premises" in parsing.read_text(encoding="utf-8")
    )


def _detect_sycophancy_controls() -> dict[str, bool]:
    return {
        "noApprovalGradient": _reward_signal_excludes_user_rating(),
        "mandatoryDissent": _destructive_in_default_perspectives(),
        "confidencePenalty": _critique_prompt_has_confidence_penalty(),
        "noStyleSelector": _no_preset_varies_by_stance(),
        # Light up as later workstreams land; detectors added alongside each.
        "directPathEpistemicRules": _direct_prompts_carry_epistemic_rules(),
        "premiseAudit": _premise_audit_enabled(),
        "deaffirmEgress": False,
        "advisoryRoute": False,
        "revisionLicence": _followup_context_has_revision_licence(),
        "verificationStep": False,
    }


def _followup_context_has_revision_licence() -> bool:
    """W7: build_followup_context licenses the model to contradict a prior turn."""
    path = ROOT / "src" / "reasoner" / "phases" / "_shared.py"
    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    return "_REVISION_LICENCE" in src and "Consistency with your own earlier answer" in src


def _provider_names() -> list[str]:
    """Display names for the direct (non-OpenRouter) fallback adapters.

    Sourced from the registry keys rather than copied prose, so a provider
    added or removed from ``_FALLBACK_PROVIDER_REGISTRY`` changes this list
    on the next commit instead of silently going stale on the site.
    """
    display = {
        "anthropic": "Anthropic", "openai": "OpenAI", "google": "Google",
        "mistral": "Mistral", "deepseek": "DeepSeek", "xai": "xAI",
        "perplexity": "Perplexity", "qwen": "Qwen",
    }
    return [display.get(name, name.title()) for name in _fallback_provider_registry()]


def _count_test_files() -> int:
    tests_dir = ROOT / "tests"
    return len(list(tests_dir.glob("*.py"))) if tests_dir.exists() else 0


# ── Patching helpers ──────────────────────────────────────────────────────────

def _patch(text: str, pattern: str, replacement: str, label: str = "") -> str:
    new, n = re.subn(pattern, replacement, text, count=1)
    if n == 0 and label:
        print(f"  [mindmap] WARNING: pattern not found in {label} — {pattern!r}", file=sys.stderr)
    return new


def _stage(path: Path) -> None:
    subprocess.run(
        ["git", "add", str(path.relative_to(ROOT))],
        cwd=ROOT, check=False, capture_output=True,
    )


# ── Per-document updaters ────────────────────────────────────────────────────

def _update_architecture_mindmap(today: str, py: int, models: int, presets: int, methods: int) -> bool:
    if not ARCHITECTURE_MINDMAP.exists():
        return False
    text = orig = ARCHITECTURE_MINDMAP.read_text(encoding="utf-8")
    f = ARCHITECTURE_MINDMAP.name

    text = _patch(text, r"\*\*Last Updated:\*\* \S+", f"**Last Updated:** {today}", f)
    # Legacy table row — present in older regenerations, absent in newer ones; skip silently
    text = re.sub(r"\| \*\*Generated\*\* \| [^\|]+ \|", f"| **Generated** | {today} |", text)
    if py:
        text = _patch(text, r"~\d+\+? source files", f"~{py} source files", f)
    if models:
        # "131+ LLM models" in prose, and "| **Models Supported** | 100+" in table
        text = re.sub(r"\b\d+\+? LLM models\b", f"{models}+ LLM models", text)
        text = re.sub(r"(\| \*\*Models Supported\*\* \| )\d+\+?", rf"\g<1>{models}+", text)
    if presets:
        text = re.sub(r"\b\d+\+? declarative presets\b", f"{presets}+ declarative presets", text)
        text = re.sub(r"(\| \*\*Presets\*\* \| )\d+\+?", rf"\g<1>{presets}+", text)
    if methods:
        text = _patch(text, r"\| \*\*Reasoning Methods\*\* \| \d+", f"| **Reasoning Methods** | {methods}", f)

    if text == orig:
        return False
    ARCHITECTURE_MINDMAP.write_text(text, encoding="utf-8")
    _stage(ARCHITECTURE_MINDMAP)
    return True


def _update_codebase_mindmap(today: str, py: int, models: int, presets: int, methods: int) -> bool:
    if not CODEBASE_MINDMAP.exists():
        return False
    text = orig = CODEBASE_MINDMAP.read_text(encoding="utf-8")
    f = CODEBASE_MINDMAP.name

    # Both plain and bold "Last updated" forms
    text = re.sub(r"(\*\*Last updated:\*\*|Last updated:) \S+", rf"\1 {today}", text)
    # Header stats: both plain "Python source files: N" and bold "**Python source files:** N"
    if py:
        text = re.sub(r"(\*\*Python source files:\*\*|Python source files:) \d+", rf"\1 {py}", text)
    if models:
        text = re.sub(r"(\*\*Models:\*\*|Models:) \d+", rf"\1 {models}", text)
    if presets:
        text = re.sub(r"(\*\*Presets:\*\*|Presets:) \d+", rf"\1 {presets}", text)
    if methods:
        text = re.sub(r"(\*\*Methods:\*\*|Methods:) \d+", rf"\1 {methods}", text)

    if text == orig:
        return False
    CODEBASE_MINDMAP.write_text(text, encoding="utf-8")
    _stage(CODEBASE_MINDMAP)
    return True


def _update_codemaps(today: str, py: int) -> int:
    if not CODEMAPS_DIR.exists():
        return 0
    updated = 0
    for md in CODEMAPS_DIR.glob("*.md"):
        text = orig = md.read_text(encoding="utf-8")
        text = re.sub(
            r"<!-- Generated: \d{4}-\d{2}-\d{2} \| Files scanned: \d+",
            f"<!-- Generated: {today} | Files scanned: {py}",
            text,
        )
        if text != orig:
            md.write_text(text, encoding="utf-8")
            _stage(md)
            updated += 1
    return updated


CAPABILITIES_TS = ROOT / "ui-next" / "src" / "lib" / "capabilities.generated.ts"


def _render_capabilities_ts(today: str, presets: int, methods: int) -> str:
    reasoning_models = _count_reasoning_models()
    routable = _count_routable_models()
    adapters = _count_provider_adapters()
    providers_literal = ", ".join(f"'{name}'" for name in _provider_names())
    tests = _count_test_files()
    controls = _detect_sycophancy_controls()
    controls_literal = ",\n".join(
        f"  {key}: {'true' if value else 'false'}" for key, value in controls.items()
    )

    return f"""/**
 * AUTO-GENERATED by scripts/update_mindmap_meta.py on {today} — do not edit
 * by hand. Regenerated on every commit from live registry, preset, and phase
 * counts (see tests/test_site_capabilities_sync.py) so marketing copy can
 * never state a capability number the code doesn't back.
 */

export const CAPABILITIES = {{
  methods: {methods},
  presets: {presets},
  directModels: {reasoning_models},
  routableModels: {routable},
  providerAdapters: {adapters},
  testFiles: {tests},
  generatedAt: '{today}',
}} as const;

/** Display names for the direct (non-OpenRouter) fallback provider adapters. */
export const PROVIDERS = [{providers_literal}] as const;

/**
 * Sycophancy controls that are actually present in the code, per commit.
 * See docs/SYCOPHANCY_MITIGATION.md and docs/plans/sycophancy-mitigation.md.
 * A control renders true only when its detector finds the mechanism at the
 * place it is used, not merely defined — landing-page copy must be gated on
 * these, never hand-written past them.
 */
export const SYCOPHANCY_CONTROLS = {{
{controls_literal},
}} as const;
"""


def _update_capabilities_ts(today: str, presets: int, methods: int) -> bool:
    CAPABILITIES_TS.parent.mkdir(parents=True, exist_ok=True)
    new_text = _render_capabilities_ts(today, presets, methods)

    if CAPABILITIES_TS.exists():
        old_text = CAPABILITIES_TS.read_text(encoding="utf-8")
        # Ignore the `generatedAt` line and the header date comment — a same-day
        # rerun with unchanged counts should not create a no-op diff.
        strip_date = lambda t: re.sub(r"(generatedAt: ')[^']+(')", r"\1\2", t).replace(today, "")
        if strip_date(old_text) == strip_date(new_text):
            return False

    CAPABILITIES_TS.write_text(new_text, encoding="utf-8")
    _stage(CAPABILITIES_TS)
    return True


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today().isoformat()
    py = _count_py_files()
    models = _count_models()
    presets = _count_presets()
    methods = _count_methods()

    changed: list[str] = []

    if _update_architecture_mindmap(today, py, models, presets, methods):
        changed.append("ARCHITECTURE_MINDMAP.md")

    if _update_codebase_mindmap(today, py, models, presets, methods):
        changed.append("docs/CODEBASE_MINDMAP.md")

    n = _update_codemaps(today, py)
    if n:
        changed.append(f"docs/CODEMAPS/ ({n} files)")

    if _update_capabilities_ts(today, presets, methods):
        changed.append("ui-next/src/lib/capabilities.generated.ts")

    if changed:
        print(
            f"[mindmap] Updated {', '.join(changed)} — "
            f"date={today}, py={py}, models={models}, presets={presets}, methods={methods}"
        )
    else:
        print("[mindmap] No metadata changes detected.")


if __name__ == "__main__":
    main()
