"""
Architecture Uncertainty: Model registry consistency.

Tests that the flow strategies, phase modules, presets, and model registry
are internally consistent. The architecture audit noted uncertainty about
whether all flow-defined methods have matching phase modules and preset
configurations.
"""

from __future__ import annotations

from pathlib import Path


# ── Flow strategy ↔ phase module consistency ─────────────────────────


def test_every_flow_method_has_phase_module() -> None:
    """Every method in the flow factory must have a corresponding phase module
    in src/reasoner/phases/. This ensures no method is registered without
    an implementation."""
    # Lazy import to avoid circular dependency chain
    import importlib
    flows_mod = importlib.import_module("reasoner.application.flows.factory")
    WorkflowFactory = flows_mod.WorkflowFactory

    factory = WorkflowFactory()

    phases_dir = (
        Path(__file__).parent.parent / "src" / "reasoner" / "phases"
    )
    existing_phases = {
        f.stem.replace("_", "-")
        for f in phases_dir.glob("*.py")
        if not f.name.startswith("_") and not f.name.startswith("vs_")
    }

    # Map flow strategy names to phase module names
    flow_to_phase = {
        "multi_perspective": "multi-perspective",
        "debate": "debate",
        "research": "research",
        "writing": "writing",
        "coding": "coding",
        "brainstorming": "brainstorming",
        "jury": "jury",
        "delphi": "delphi",
        "scientific": "scientific",
        "socratic": "socratic",
        "pre_mortem": "pre-mortem",
        "bayesian": "bayesian",
        "dialectical": "dialectical",
        "analogical": "analogical",
        "cove": "cove",
        "sot": "sot",
        "tot": "tot",
        "pot": "pot",
        "self_discover": "self-discover",
        "article": None,  # article pipeline uses shared writing/research phases
    }

    for flow_name, phase_name in flow_to_phase.items():
        if phase_name is None:
            continue  # Article is a composite — OK
        assert factory.is_migrated(flow_name)
        assert phase_name in existing_phases, (
            f"Flow '{flow_name}' has no matching phase module at "
            f"phases/{phase_name.replace('-', '_')}.py"
        )


def test_phase_modules_importable() -> None:
    """Every phase module under src/reasoner/phases/ must be importable
    without errors (no syntax errors, missing imports, etc.)."""
    import importlib

    phases_dir = (
        Path(__file__).parent.parent / "src" / "reasoner" / "phases"
    )

    for f in phases_dir.glob("*.py"):
        if f.name.startswith("__"):
            continue
        module_name = f"reasoner.phases.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            assert mod is not None
        except ImportError as exc:
            # If module depends on optional deps, skip
            if "No module named" in str(exc):
                missing = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
                if any(skip in missing for skip in ["anthropic", "openai", "google_genai", "httpx"]):
                    continue  # Optional dependencies not installed
            raise


# ── Preset ↔ method consistency ──────────────────────────────────────


def test_preset_methods_map_to_flow_strategies() -> None:
    """Every preset's derived method must map to a registered flow strategy.
    PipelinePreset has no .method field — method is derived from preset name
    via get_method_from_preset()."""
    from reasoner.application.flows.factory import WorkflowFactory
    from reasoner.domain.preset_registry import PRESETS
    from reasoner.domain.preset_core import get_method_from_preset

    factory = WorkflowFactory()

    for preset_id, preset in PRESETS.items():
        method = get_method_from_preset(preset_id)
        norm_method = method.replace("-", "_")
        # Known: cross_language has no flow strategy — it uses multi_perspective fallback.
        # The cross-language translation is handled by the pipeline core, not a method flow.
        if norm_method == "cross_language":
            continue
        assert factory.is_migrated(norm_method), (
            f"Preset '{preset_id}' derives method '{method}' which is not "
            "registered in WorkflowFactory."
        )


def test_preset_models_in_registry() -> None:
    """Every model referenced in presets must exist in the model registry."""
    from reasoner.domain.preset_registry import PRESETS
    from reasoner.infrastructure.llm.registry import _REGISTRY

    for preset_id, preset in PRESETS.items():
        # Check primary model
        assert preset.primary_id in _REGISTRY, (
            f"Preset '{preset_id}' primary model '{preset.primary_id}' "
            "not found in model registry."
        )

        # Check routing models
        for role, model_id in preset.routing.items():
            assert model_id in _REGISTRY, (
                f"Preset '{preset_id}' routing role '{role}' uses model "
                f"'{model_id}' which is not in the registry."
            )

        # Check fallback models
        for role, model_id in preset.fallback_routing.items():
            assert model_id in _REGISTRY, (
                f"Preset '{preset_id}' fallback role '{role}' uses model "
                f"'{model_id}' which is not in the registry."
            )


def test_model_registry_keys_are_valid() -> None:
    """Every model in the registry must have required fields."""
    from reasoner.infrastructure.llm.registry import _REGISTRY

    required_keys = {"model", "env"}
    for model_id, cfg in _REGISTRY.items():
        for key in required_keys:
            assert key in cfg, (
                f"Model '{model_id}' in registry missing required key '{key}'"
            )

        # If cls is "compat", must have "base"
        if cfg.get("cls") == "compat":
            assert "base" in cfg, (
                f"Compat model '{model_id}' missing 'base' URL"
            )


def test_method_slugs_are_consistent() -> None:
    """_METHOD_TO_SLUG keys should be case-foldable to registered methods."""
    from reasoner.domain.preset_core import _METHOD_TO_SLUG
    from reasoner.application.flows.factory import WorkflowFactory

    factory = WorkflowFactory()

    for key, slug in _METHOD_TO_SLUG.items():
        # The slug (with hyphens) should be resolvable from key
        assert factory.is_migrated(slug), (
            f"Method slug '{slug}' (from key '{key}') not found in factory. "
            "Check _METHOD_TO_SLUG consistency."
        )


# ── Phase timeout consistency ─────────────────────────────────────────


def test_phase_timeout_has_default() -> None:
    """PHASE_TIMEOUTS must include a 'default' key."""
    from reasoner.core.constants import PHASE_TIMEOUTS, get_phase_timeout

    assert "default" in PHASE_TIMEOUTS
    # Calling get_phase_timeout with unknown phase should return default
    result = get_phase_timeout("NonExistentPhase")
    assert result == PHASE_TIMEOUTS["default"]


def test_phase_token_budget_has_default() -> None:
    """PHASE_TOKEN_BUDGETS must include a 'default' key."""
    from reasoner.core.constants import PHASE_TOKEN_BUDGETS, get_token_budget

    assert "default" in PHASE_TOKEN_BUDGETS
    result = get_token_budget("nonexistent_role")
    assert result == PHASE_TOKEN_BUDGETS["default"]


# ── Vertical solution (VS) phases ─────────────────────────────────────


def test_vs_phase_modules_exist() -> None:
    """All 9 documented VS phases must have corresponding modules."""
    expected_vs_modules = [
        "vs_behavioral_audit",
        "vs_calibration",
        "vs_claim_extraction",
        "vs_conflict_surfacing",
        "vs_coverage_audit",
        "vs_decomposition",
        "vs_generation",
        "vs_probe_generation",
        "vs_verification_routing",
    ]

    phases_dir = (
        Path(__file__).parent.parent / "src" / "reasoner" / "phases"
    )

    for mod_name in expected_vs_modules:
        mod_path = phases_dir / f"{mod_name}.py"
        assert mod_path.is_file(), (
            f"VS phase module {mod_name}.py missing from phases/ directory"
        )


def test_vs_phase_modules_importable() -> None:
    """All VS phase modules must be importable."""
    import importlib

    vs_modules = [
        "vs_behavioral_audit",
        "vs_calibration",
        "vs_claim_extraction",
        "vs_conflict_surfacing",
        "vs_coverage_audit",
        "vs_decomposition",
        "vs_generation",
        "vs_probe_generation",
        "vs_verification_routing",
    ]

    for mod_name in vs_modules:
        module_path = f"reasoner.phases.{mod_name}"
        try:
            mod = importlib.import_module(module_path)
            assert mod is not None
        except ImportError as exc:
            if "No module named" in str(exc):
                missing = str(exc).split("'")[1] if "'" in str(exc) else str(exc)
                if any(skip in missing for skip in ["anthropic", "openai", "google_genai", "httpx"]):
                    continue
            raise
