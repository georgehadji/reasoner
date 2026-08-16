"""Tests for cross-language reasoning and DeepL translation."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from reasoner.models import PipelineState, FinalSolution, MetaCognitiveAudit
from reasoner.infrastructure.translation.deepl_client import (
    DeepLClient,
    get_deepl_client,
    reset_deepl_client,
    FREE_BASE_URL,
    PAID_BASE_URL,
)


def _make_mock_router():
    """Create a minimal mock ProviderRouter for ReasonerPipeline tests."""
    mock_provider = MagicMock()
    mock_provider.model = "test-model"
    mock_router = MagicMock()
    mock_router.primary = mock_provider
    mock_router.routing_table = {}
    mock_router.fallback_table = {}
    mock_router.verbose = False
    mock_router.get.return_value = mock_provider
    return mock_router


def _make_final_solution(core_solution: str = "") -> FinalSolution:
    """Create a FinalSolution with minimal required fields."""
    return FinalSolution(
        core_solution=core_solution,
        critical_insights=[],
        action_blueprint=[],
        open_questions=[],
        claim_labels={},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="",
            dominant_bias="",
            remaining_uncertainty="",
            assumption_failure_impact="",
            non_obvious_insight="",
        ),
    )


class TestDeepLClient:
    """Unit tests for the DeepL API client."""

    def test_free_key_uses_free_endpoint(self):
        """Free-tier keys (ending with :fx) should use the free endpoint."""
        client = DeepLClient(api_key="test-key:fx")
        assert client.base_url == FREE_BASE_URL

    def test_paid_key_uses_paid_endpoint(self):
        """Paid keys should use the paid endpoint."""
        client = DeepLClient(api_key="test-key")
        assert client.base_url == PAID_BASE_URL

    @pytest.mark.asyncio
    async def test_translate_success(self):
        """Happy path: translate text and return parsed response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "translations": [
                {
                    "detected_source_language": "DE",
                    "text": "Hello world",
                }
            ]
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(DeepLClient, "_get_client", return_value=mock_client):
            client = DeepLClient(api_key="test-key")
            result = await client.translate("Hallo Welt", target_lang="EN")
            assert result["text"] == "Hello world"
            assert result["detected_source_language"] == "DE"

            # Verify the request
            call_args = mock_client.post.call_args
            assert call_args[1]["headers"]["Authorization"] == "DeepL-Auth-Key test-key"
            assert call_args[1]["data"]["text"] == ["Hallo Welt"]
            assert call_args[1]["data"]["target_lang"] == "EN"

    @pytest.mark.asyncio
    async def test_translate_with_source_lang(self):
        """Providing a source language should include it in the request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "translations": [{"detected_source_language": "DE", "text": "Hello"}]
        }
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(DeepLClient, "_get_client", return_value=mock_client):
            client = DeepLClient(api_key="test-key")
            await client.translate("Hallo", target_lang="EN", source_lang="DE")
            call_args = mock_client.post.call_args
            assert call_args[1]["data"]["source_lang"] == "DE"

    @pytest.mark.asyncio
    async def test_translate_api_error(self):
        """Non-200 response should raise RuntimeError."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(DeepLClient, "_get_client", return_value=mock_client):
            client = DeepLClient(api_key="test-key")
            with pytest.raises(RuntimeError, match="DeepL API error 403"):
                await client.translate("test", target_lang="DE")

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Health check should return True when API responds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(DeepLClient, "_get_client", return_value=mock_client):
            client = DeepLClient(api_key="test-key")
            assert await client.health_check() is True

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        """Health check without key should return False."""
        # api_key=None falls back to settings.DEEPL_API_KEY, not os.getenv, so
        # patching os.getenv left a real key in place on any machine that has
        # one configured. Clear the resolved key to test the no-key branch.
        client = DeepLClient(api_key=None)
        client.api_key = ""
        assert await client.health_check() is False


class TestCrossLanguagePipeline:
    """Unit tests for cross-language pipeline phases."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        reset_deepl_client()
        yield
        reset_deepl_client()

    @pytest.mark.asyncio
    async def test_translate_in_skips_english(self):
        """English problems should not be translated."""
        from reasoner.pipeline import ReasonerPipeline

        router = _make_mock_router()
        pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
        state = PipelineState(problem="Hello world", language="English")
        await pipeline._phase_cross_language_translate_in(state)
        assert state.problem == "Hello world"
        assert state.cross_language_state == {}

    @pytest.mark.asyncio
    async def test_translate_in_translates_non_english(self):
        """Non-English problems should be translated to English."""
        from reasoner.pipeline import ReasonerPipeline

        with patch("reasoner.infrastructure.translation.deepl_client.DeepLClient.translate", new_callable=AsyncMock) as mock_translate:
            mock_translate.return_value = {
                "text": "Hello world",
                "detected_source_language": "DE",
            }
            router = _make_mock_router()
            pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
            state = PipelineState(problem="Hallo Welt", language="German")
            await pipeline._phase_cross_language_translate_in(state)
            assert state.problem == "Hello world"
            assert state.cross_language_state["original_problem"] == "Hallo Welt"
            assert state.cross_language_state["source_language"] == "DE"
            assert state.cross_language_state["direction"] == "in"

    @pytest.mark.asyncio
    async def test_translate_in_graceful_failure(self):
        """If translation fails, the original problem should be preserved."""
        from reasoner.pipeline import ReasonerPipeline

        with patch("reasoner.infrastructure.translation.deepl_client.DeepLClient.translate", new_callable=AsyncMock) as mock_translate:
            mock_translate.side_effect = RuntimeError("API down")
            router = _make_mock_router()
            pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
            state = PipelineState(problem="Hallo Welt", language="German")
            await pipeline._phase_cross_language_translate_in(state)
            assert state.problem == "Hallo Welt"  # unchanged
            assert len(state.errors) == 1
            assert "translation-in error" in state.errors[0]

    @pytest.mark.asyncio
    async def test_translate_out_no_state(self):
        """If no cross_language_state exists, skip translation out."""
        from reasoner.pipeline import ReasonerPipeline

        router = _make_mock_router()
        pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
        state = PipelineState(problem="Hello")
        await pipeline._phase_cross_language_translate_out(state)
        assert state.cross_language_state == {}

    @pytest.mark.asyncio
    async def test_translate_out_success(self):
        """Synthesis should be translated back to source language."""
        from reasoner.pipeline import ReasonerPipeline

        with patch("reasoner.infrastructure.translation.deepl_client.DeepLClient.translate", new_callable=AsyncMock) as mock_translate:
            mock_translate.return_value = {
                "text": "Hallo Welt",
                "detected_source_language": "EN",
            }
            router = _make_mock_router()
            pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
            state = PipelineState(problem="Hello world")
            # translate_out gates on pivot_active/output_language now;
            # cross_language_state alone is legacy resume data and makes the
            # phase a no-op, so these tests silently asserted nothing.
            state.pivot_active = True
            state.output_language = "German"
            state.cross_language_state = {"source_language": "DE"}
            state.final_solution = _make_final_solution(core_solution="Hello world")
            await pipeline._phase_cross_language_translate_out(state)
            assert state.final_solution.core_solution == "Hallo Welt"
            assert state.cross_language_state["translated_synthesis"] == "Hallo Welt"
            assert state.cross_language_state["direction"] == "out"

    @pytest.mark.asyncio
    async def test_translate_out_graceful_failure(self):
        """If back-translation fails, synthesis should remain in English."""
        from reasoner.pipeline import ReasonerPipeline

        with patch("reasoner.infrastructure.translation.deepl_client.DeepLClient.translate", new_callable=AsyncMock) as mock_translate:
            mock_translate.side_effect = RuntimeError("API down")
            router = _make_mock_router()
            pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
            state = PipelineState(problem="Hello world")
            state.pivot_active = True
            state.output_language = "German"
            state.cross_language_state = {"source_language": "DE"}
            state.final_solution = _make_final_solution(core_solution="Hello world")
            await pipeline._phase_cross_language_translate_out(state)
            assert state.final_solution.core_solution == "Hello world"  # unchanged
            assert len(state.errors) == 1
            assert "translation-out error" in state.errors[0]


class TestCrossLanguagePreset:
    """Tests for preset configuration."""

    def test_preset_exists(self):
        """Cross-language presets should be registered."""
        from reasoner.domain.preset_registry import PRESETS
        assert "cross-language-budget" in PRESETS
        assert "cross-language-premium" in PRESETS

    def test_preset_requires_deepl_key(self):
        """Cross-language presets should require DEEPL_API_KEY."""
        from reasoner.domain.preset_registry import PRESETS
        from reasoner.domain.preset_registry import get_preset
        # PRESETS holds raw config dicts; get_preset() builds the PipelinePreset.
        preset = get_preset("cross-language-budget")
        assert "DEEPL_API_KEY" in preset.required_env_vars

    def test_method_extraction(self):
        """Preset names should map to the cross_language method."""
        from reasoner.domain.preset_core import get_method_from_preset
        assert get_method_from_preset("cross-language-budget") == "cross_language"
        assert get_method_from_preset("cross-language-premium") == "cross_language"

    def test_pipeline_method_extraction(self):
        """ReasonerPipeline should extract cross_language from preset name."""
        from reasoner.pipeline import ReasonerPipeline
        router = _make_mock_router()
        pipeline = ReasonerPipeline(router=router, preset_name="cross-language-budget")
        assert pipeline._get_method_from_preset() == "cross_language"


class TestCrossLanguageSerializer:
    """Tests for cross-language state serialization."""

    def test_cross_language_metadata_in_synthesis(self):
        """Serializer should include cross_language metadata when present."""
        from reasoner.api.serializers import _ser_5

        state = PipelineState(problem="Hallo")
        state.final_solution = _make_final_solution(core_solution="Hello")
        state.cross_language_state = {
            "source_language": "DE",
            "original_problem": "Hallo",
            "direction": "out",
        }
        result = _ser_5(state)
        assert result["cross_language"]["source_language"] == "DE"
        assert result["cross_language"]["original_problem"] == "Hallo"
        assert result["cross_language"]["translated"] is True

    def test_no_cross_language_when_empty(self):
        """Serializer should omit cross_language key when state is empty."""
        from reasoner.api.serializers import _ser_5

        state = PipelineState(problem="Hello")
        state.final_solution = _make_final_solution(core_solution="Hello")
        result = _ser_5(state)
        assert "cross_language" not in result
