"""An auto run that becomes an article must be routed by an article preset.

Every auto run whose method resolves to "writing" executes ArticleFlow
(api/execution/pipeline.py turns it into "article"), but preflight built the
router for the *writing* preset. writing-budget routes none of the article roles
(article_sot_skeleton, article_humanize, ...), so they fell back to its
primary_id, qwen3.5-flash: the model registry.py documents as spending its whole
budget narrating "Thinking Process:" instead of answering. Observed 2026-11-09:
outline and humanize both failed to parse, and the copy edit published the
narration as the article.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner.application.orchestrator import PipelineOrchestrator


def _gate(method: str) -> SimpleNamespace:
    return SimpleNamespace(
        action="pipeline",
        method=method,
        confidence=0.9,
        reasoning="",
        alternatives=None,
        augmentation_methods=["none"],
    )


def _preset_service() -> MagicMock:
    svc = MagicMock()
    svc.resolve.return_value = ("auto-budget", True, "budget")
    svc.build_router.return_value = ("auto-budget", MagicMock(name="auto-router"))
    svc.build_auto_router.side_effect = lambda method, tier, **kw: (
        f"{method}-{tier}",
        MagicMock(name=f"{method}-router"),
    )
    return svc


async def _preflight(problem: str, gate_method: str, **req_fields):
    svc = _preset_service()
    orch = PipelineOrchestrator(preset_service=svc, pipeline_service=MagicMock())
    req = SimpleNamespace(problem=problem, preset="auto-budget", **req_fields)
    with (
        patch.object(orch, "_recall_neuro_context", AsyncMock(return_value=[])),
        patch("reasoner.application.orchestrator.HyperGateAgent"),
        patch("reasoner.application.services.gate_service.build_hypergate_router"),
        patch(
            "reasoner.application.services.gate_service.run_gate_cached",
            AsyncMock(return_value=_gate(gate_method)),
        ),
    ):
        decision = await orch.preflight(req)
    return decision, svc


@pytest.mark.asyncio
async def test_gate_selected_writing_is_routed_by_the_article_preset():
    decision, svc = await _preflight("Compare two databases for me", "writing")

    assert decision.auto_selected_method == "writing"  # still becomes ArticleFlow
    assert decision.effective_preset_name == "article-budget"
    assert svc.build_auto_router.call_args.args[:2] == ("article", "budget")


@pytest.mark.asyncio
async def test_detected_article_request_is_routed_by_the_article_preset():
    decision, _ = await _preflight("Write an article about SQL tautologies", "debate")

    assert decision.auto_selected_method == "writing"
    assert decision.effective_preset_name == "article-budget"


@pytest.mark.asyncio
async def test_other_auto_methods_keep_their_own_preset():
    decision, _ = await _preflight("Should we raise VC money?", "debate")

    assert decision.auto_selected_method == "debate"
    assert decision.effective_preset_name == "debate-budget"


@pytest.mark.asyncio
async def test_custom_routing_is_never_replaced():
    decision, svc = await _preflight(
        "Write an article about SQL tautologies", "writing", routing={"primary": "gpt-5"}
    )

    assert decision.effective_preset_name == "auto-budget"
    svc.build_auto_router.assert_not_called()


@pytest.mark.asyncio
async def test_a_named_method_is_not_overridden_by_article_detection():
    """"use the iterative-critique method to propose what subject to write an
    article ..." matches the article regex, but the user named the method."""
    decision, svc = await _preflight(
        "use the iterative-critique method to propose what subject to write an article on AI",
        "iterative_critique",
    )

    assert decision.auto_selected_method == "iterative_critique"
    assert decision.effective_preset_name == "iterative_critique-budget"
    assert all(c.args[0] != "article" for c in svc.build_auto_router.call_args_list)
