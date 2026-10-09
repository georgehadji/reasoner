"""Regression tests: agent_model override must reach the fusion role.

`PresetService.build_router()` / `build_auto_router()` override `agent_model`
onto a fixed set of routing roles. That set used to be
("synthesis", "classification", "decomposition") — the roles that predated the
WorkflowStrategy refactor. "fusion" (domain/preset_core.py's
_KNOWN_ROUTING_ROLES) replaced the separate classification/decomposition
phases (application/pipeline.py's ReasonerPipeline.run() calls
`call_llm(role="fusion", ...)`, not "classification"/"decomposition"), so a
configured follow-up agent_model silently never reached that phase's routing
entry even though the legacy roles were still (harmlessly) overridden.
"""

from reasoner.application.services.preset_service import PresetService
from reasoner.infrastructure.llm.registry import resolved_model_of
from reasoner.presets import FOLLOWUP_AGENT_MODELS

# Real registered aliases (not literals): build_provider() raises on an
# unknown model ID, and a literal like "grok-4.20" goes stale across version
# bumps — see tests/test_presets.py::TestFollowupAgentModels.
_BUDGET_AGENT_MODEL = FOLLOWUP_AGENT_MODELS["budget"]
_PREMIUM_AGENT_MODEL = FOLLOWUP_AGENT_MODELS["premium"]


def test_build_router_agent_model_overrides_fusion_role():
    service = PresetService()
    _, router = service.build_router(
        "multi-perspective-budget",
        agent_model=_BUDGET_AGENT_MODEL,
    )

    expected = resolved_model_of(_BUDGET_AGENT_MODEL).lstrip("~")
    # multi-perspective-budget's own "fusion" entry ("qwen3.5-9b") differs from
    # its "synthesis" entry ("llama-4-maverick") by default, so this only
    # passes if the override actually reached the role rather than the preset's
    # own routing surviving underneath it.
    assert router.routing_table["fusion"].model.lstrip("~") == expected
    assert router.routing_table["synthesis"].model.lstrip("~") == expected


def test_build_auto_router_agent_model_overrides_fusion_role():
    service = PresetService()
    _, router = service.build_auto_router(
        method="multi-perspective",
        tier="budget",
        agent_model=_PREMIUM_AGENT_MODEL,
    )

    expected = resolved_model_of(_PREMIUM_AGENT_MODEL).lstrip("~")
    assert router.routing_table["fusion"].model.lstrip("~") == expected
    assert router.routing_table["synthesis"].model.lstrip("~") == expected
