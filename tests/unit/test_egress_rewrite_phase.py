"""Layer B: divergence scoring, model selection, and the 5 rewrite guards."""

from __future__ import annotations

import pytest

from reasoner.application.flows.egress_rewrite_phase import run_egress_rewrite_phase
from reasoner.domain.core_types import FinalSolution, MetaCognitiveAudit
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.watermark.divergence import lexical_divergence, select_most_diverged
from reasoner.infrastructure.watermark.rewriter import build_rewrite_prompt, select_rewrite_model


def _final_solution(core_solution: str) -> FinalSolution:
    return FinalSolution(
        core_solution=core_solution,
        critical_insights=[],
        action_blueprint=[],
        open_questions=[],
        claim_labels={},
        meta_audit=MetaCognitiveAudit("", "", "", "", ""),
    )


class FakeRouter:
    """Minimal stand-in for ProviderRouter -- only routing_table is used here."""

    def __init__(self):
        self.routing_table: dict[str, object] = {}


class FakeServices:
    def __init__(self, response: str = "", raise_error: bool = False):
        self.response = response
        self.raise_error = raise_error
        self.logs: list[tuple[str, str]] = []
        self.router = FakeRouter()

    def log(self, phase, message, state):
        self.logs.append((phase, message))

    async def call_llm(self, role, system_prompt, user_prompt, state, **kwargs):
        if self.raise_error:
            raise RuntimeError("llm unavailable")
        return self.response, {}


class _StubRegistryPort:
    """Stub ModelRegistryPort -- the phase only ever calls get_provider()."""

    def get_provider(self, model_id: str, api_key: str | None = None) -> object:
        return object()

    def contains(self, model_id: str) -> bool:
        return True

    def entry(self, model_id: str) -> dict | None:
        return {}


@pytest.fixture
def layer_b_on(monkeypatch):
    """Enable Layer B and stub provider construction at the port boundary.

    Patches the port, not infrastructure.llm.registry: the phase resolves its
    provider through get_model_registry_port(), which raises unless an adapter
    was injected at startup. Stubbing it keeps these tests hermetic -- no real
    provider, no API key, no network -- regardless of injection state.
    """
    import reasoner.application.flows.egress_rewrite_phase as mod
    import reasoner.core.ports.model_registry_port as registry_port
    from reasoner.core.settings import settings

    monkeypatch.setattr(settings, "WATERMARK_LAYER_B_ENABLED", True)
    monkeypatch.setattr(mod, "select_rewrite_model", lambda origin: "claude-sonnet")
    monkeypatch.setattr(registry_port, "get_model_registry_port", lambda: _StubRegistryPort())
    return mod


class TestDivergence:
    def test_identical_text_zero_divergence(self):
        assert lexical_divergence("the quick brown fox", "the quick brown fox") == 0.0

    def test_fully_different_text_high_divergence(self):
        assert lexical_divergence("apple banana cherry", "xyz qrs tuv") == 1.0

    def test_select_most_diverged_picks_highest_score(self):
        original = "the quick brown fox jumps"
        diverged = "a totally different sentence entirely"
        selection = select_most_diverged(original, ["the quick brown fox jumps", diverged])
        assert selection.index == 1

    def test_select_most_diverged_penalizes_length_drift(self):
        original = "one two three four five"
        # candidate is >2x longer -- penalty should make an equally-diverged
        # short candidate win instead.
        short = "six seven eight nine ten"
        long = "six seven eight nine ten " * 5
        selection = select_most_diverged(original, [short, long])
        assert selection.index == 0


class TestBuildRewritePrompt:
    @pytest.mark.parametrize("strategy", ["paraphrase", "humanize", "backtranslate", "structural"])
    def test_known_strategies_embed_text(self, strategy):
        prompt = build_rewrite_prompt(strategy, "hello world")
        assert "hello world" in prompt

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError):
            build_rewrite_prompt("nonexistent", "text")


class TestSelectRewriteModel:
    def test_empty_origin_returns_none(self):
        assert select_rewrite_model("") is None

    def test_finds_cross_bloc_candidate(self):
        # claude-sonnet is Anthropic/US; a real cross-bloc candidate must exist
        # in the whitelist (CN or EU) for this to return non-None.
        model = select_rewrite_model("claude-sonnet")
        assert model is not None
        assert "image" not in model


class TestEgressRewritePhase:
    @pytest.mark.asyncio
    async def test_noop_when_layer_b_disabled(self, monkeypatch):
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "WATERMARK_LAYER_B_ENABLED", False)
        state = PipelineState()
        state.final_solution = _final_solution("original text")
        services = FakeServices(response="rewritten text")

        await run_egress_rewrite_phase(state, services)

        assert state.final_solution.core_solution == "original text"
        assert not services.logs

    @pytest.mark.asyncio
    async def test_article_method_is_skipped(self, layer_b_on):
        """The article flow's deliverable is writing_state['final_article'],
        already through two dedicated editorial passes (humanize +
        developmental edit) -- core_solution here is a short generic
        synthesis summary the reader never sees. Rewriting it protects
        nothing and the guards reject it near-certainly (confirmed live
        2026-08-28: 542-char summary, 3.8x length drift). See
        docs/plans/article-flow-truncation-remediation.md W5.
        """
        state = PipelineState()
        state.method = "article"
        state.final_solution = _final_solution("original text")
        services = FakeServices(response="rewritten text")

        await run_egress_rewrite_phase(state, services)

        assert state.final_solution.core_solution == "original text"
        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is False
        assert "article" in report["rejected_reason"]
        # Skipped before any provider was ever resolved.
        assert "egress_rewrite" not in services.router.routing_table

    @pytest.mark.asyncio
    async def test_no_candidate_model_rejects(self, monkeypatch, layer_b_on):
        monkeypatch.setattr(layer_b_on, "select_rewrite_model", lambda origin: None)
        state = PipelineState()
        state.final_solution = _final_solution("original text")
        services = FakeServices(response="rewritten text")

        await run_egress_rewrite_phase(state, services)

        assert state.final_solution.core_solution == "original text"
        assert state.meta.provenance_report["egress_rewrite"]["rewritten"] is False

    @pytest.mark.asyncio
    async def test_selected_model_is_bound_to_the_role(self, layer_b_on):
        """ProviderRouter falls back to the preset primary for unknown roles, so
        the phase must bind its chosen model or the cross-bloc guarantee is fake."""
        state = PipelineState()
        state.final_solution = _final_solution("the result was 42 percent complete")
        services = FakeServices(response="the outcome reached 42 percent completion")

        await run_egress_rewrite_phase(state, services)

        assert "egress_rewrite" in services.router.routing_table

    @pytest.mark.asyncio
    async def test_dropped_citation_rejects(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("see https://example.com/source for details")
        services = FakeServices(response="see the source for details, citation removed")

        await run_egress_rewrite_phase(state, services)

        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is False
        assert "citation" in report["rejected_reason"]
        assert state.final_solution.core_solution == "see https://example.com/source for details"

    @pytest.mark.asyncio
    async def test_url_with_trailing_period_is_not_a_dropped_citation(self, layer_b_on):
        """Regression: a live model ended a sentence with the URL, so the match
        captured 'https://example.com/source.' and the guard falsely rejected."""
        state = PipelineState()
        state.final_solution = _final_solution("details live at https://example.com/source for now")
        services = FakeServices(response="the writeup is at https://example.com/source.")

        await run_egress_rewrite_phase(state, services)

        assert state.meta.provenance_report["egress_rewrite"]["rewritten"] is True

    @pytest.mark.asyncio
    async def test_altered_number_rejects(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("the result was 42 percent")
        services = FakeServices(response="the result was 99 percent")

        await run_egress_rewrite_phase(state, services)

        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is False
        assert "number" in report["rejected_reason"]

    @pytest.mark.asyncio
    async def test_spelled_out_number_is_not_a_mismatch(self, layer_b_on):
        """Regression: paraphrasing legitimately turns '3 regions' into 'three
        regions'; strict set equality rejected valid live rewrites for it."""
        state = PipelineState()
        state.final_solution = _final_solution("the rollout covered 3 regions in total")
        services = FakeServices(response="in total, the rollout spanned three regions")

        await run_egress_rewrite_phase(state, services)

        assert state.meta.provenance_report["egress_rewrite"]["rewritten"] is True

    @pytest.mark.asyncio
    async def test_changed_identifier_rejects(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("the `auth_middleware` module was slow")
        services = FakeServices(response="the `authMiddleware` module was slow")

        await run_egress_rewrite_phase(state, services)

        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is False
        assert "identifier" in report["rejected_reason"]

    @pytest.mark.asyncio
    async def test_length_drift_rejects(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("short original text here")
        services = FakeServices(response="way " * 40 + "too long")  # >1.6x

        await run_egress_rewrite_phase(state, services)

        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is False
        assert "length drift" in report["rejected_reason"]

    @pytest.mark.asyncio
    async def test_llm_failure_keeps_original(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("original text")
        services = FakeServices(raise_error=True)

        await run_egress_rewrite_phase(state, services)

        assert state.final_solution.core_solution == "original text"
        assert "failed" in state.meta.provenance_report["egress_rewrite"]["rejected_reason"]

    @pytest.mark.asyncio
    async def test_accepted_rewrite_replaces_core_solution(self, layer_b_on):
        state = PipelineState()
        state.final_solution = _final_solution("the result was 42 percent complete")
        services = FakeServices(response="the outcome reached 42 percent completion")

        await run_egress_rewrite_phase(state, services)

        report = state.meta.provenance_report["egress_rewrite"]
        assert report["rewritten"] is True
        assert report["model"] == "claude-sonnet"
        assert state.final_solution.core_solution == "the outcome reached 42 percent completion"
