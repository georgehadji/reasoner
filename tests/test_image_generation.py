"""Tests for image generation service and presets."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner.infrastructure.llm.image_generation import (
    _heuristic_policy_safe_rewrite,
    _normalize_image_data,
    _rewrite_prompt_for_policy_safety,
    _resolve_first_image_candidate,
    _should_retry_with_policy_safe_prompt,
    _should_prefer_images_api,
    _get_modalities,
    _resolve_model_config,
    generate_images,
    generate_image_with_model,
    ImageGenerationError,
)
from reasoner.core.constants_limits import (
    IMAGE_GEN_FALLBACKS,
    IMAGE_GEN_IMAGE_COUNT,
    IMAGE_GEN_PRESETS,
)
from reasoner.domain.preset_registry import PRESETS, get_preset


class TestResolveModelConfig:
    def test_resolves_known_aliases(self):
        assert "google/gemini-2.5-flash-image" == _resolve_model_config("gemini-flash-image")["model"]
        assert "google/gemini-3-pro-image" == _resolve_model_config("gemini-pro-image")["model"]
        assert "qwen/qwen-image-3" == _resolve_model_config("qwen-image-3")["model"]
        assert "openai/gpt-5-image" == _resolve_model_config("gpt-5-image")["model"]
        assert "openai/gpt-5-image-mini" == _resolve_model_config("gpt-5-image-mini")["model"]

    def test_raises_on_unknown_alias(self):
        with pytest.raises(ValueError, match="Unknown image generation model alias"):
            _resolve_model_config("nonexistent-model")


class TestGetModalities:
    def test_gemini_returns_text_image(self):
        assert _get_modalities("google/gemini-2.5-flash-image") == ["text", "image"]
        assert _get_modalities("google/gemini-3-pro-image-preview") == ["text", "image"]

    def test_gpt_image_returns_text_image(self):
        assert _get_modalities("openai/gpt-5-image") == ["text", "image"]
        assert _get_modalities("openai/gpt-5-image-mini") == ["text", "image"]

    def test_unknown_returns_image_only(self):
        assert _get_modalities("black-forest-labs/flux.2-pro") == ["image"]


class TestTransportSelection:
    def test_image_models_prefer_images_api(self):
        assert _should_prefer_images_api("google/gemini-3-pro-image-preview") is True
        assert _should_prefer_images_api("openai/gpt-5-image") is True
        assert _should_prefer_images_api("black-forest-labs/flux.2-pro") is True

    def test_non_image_models_do_not_prefer_images_api(self):
        assert _should_prefer_images_api("google/gemini-2.5-flash") is False


class TestImageNormalization:
    def test_raw_jpeg_base64_keeps_jpeg_mime(self):
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"test-jpeg-payload" * 40
        encoded = base64.b64encode(jpeg_bytes).decode("ascii")

        normalized = _normalize_image_data(encoded)

        assert normalized is not None
        assert normalized.startswith("data:image/jpeg;base64,")

    @pytest.mark.asyncio
    async def test_remote_image_candidate_is_downloaded(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation._download_image_url",
            new_callable=AsyncMock,
        ) as mock_download:
            mock_download.return_value = "data:image/webp;base64,remote-image"

            result = await _resolve_first_image_candidate(
                {"image_url": {"url": "https://cdn.example.com/generated?id=123"}}
            )

        assert result == "data:image/webp;base64,remote-image"
        mock_download.assert_awaited_once()


class TestPolicyRetryHeuristics:
    def test_retries_when_policy_block_detected(self):
        errors = [
            "flux.2-flex: API call failed for flux.2-flex: Request Moderated",
            "gemini-flash-image: Could not extract image from gemini-flash-image response.",
        ]
        assert _should_retry_with_policy_safe_prompt(errors) is True

    def test_retries_when_multiple_non_image_responses_detected(self):
        errors = [
            "gemini-flash-image: Could not extract image from gemini-flash-image response.",
            "gpt-5-image-mini: No extractable image data or text from gpt-5-image-mini",
        ]
        assert _should_retry_with_policy_safe_prompt(errors) is True

    def test_does_not_retry_on_generic_transport_errors_only(self):
        errors = [
            "gemini-flash-image: API call failed for gemini-flash-image: timeout",
            "gpt-5-image-mini: API call failed for gpt-5-image-mini: timeout",
        ]
        assert _should_retry_with_policy_safe_prompt(errors) is False

    def test_heuristic_rewrite_scrubs_known_brands(self):
        rewritten = _heuristic_policy_safe_rewrite(
            "A whimsical Disney and Asterix crossover in Ancient Greece featuring Mickey Mouse and Donald Duck"
        )

        assert rewritten is not None
        lowered = rewritten.lower()
        assert "disney" not in lowered
        assert "asterix" not in lowered
        assert "mickey mouse" not in lowered
        assert "donald duck" not in lowered
        assert "ancient greece" in lowered
        assert "original" in lowered

    def test_heuristic_rewrite_scrubs_ducktales_names(self):
        rewritten = _heuristic_policy_safe_rewrite(
            "A vivid portrait of Scrooge McDuck, Fethry Duck, Magica De Spell, and Gyro Gearloose exploring a neon city"
        )

        assert rewritten is not None
        lowered = rewritten.lower()
        assert "scrooge mcduck" not in lowered
        assert "fethry" not in lowered
        assert "magica de spell" not in lowered
        assert "gyro gearloose" not in lowered
        assert "original" in lowered

    def test_heuristic_rewrite_scrubs_duck_family_and_duckburg(self):
        rewritten = _heuristic_policy_safe_rewrite(
            "Duck family sightseeing in Duckburg with Huey, Dewey, and Louie"
        )

        assert rewritten is not None
        lowered = rewritten.lower()
        assert "duck family" not in lowered
        assert "duckburg" not in lowered
        assert "huey" not in lowered
        assert "dewey" not in lowered
        assert "louie" not in lowered
        assert "original" in lowered

    @pytest.mark.asyncio
    async def test_policy_rewrite_falls_back_to_heuristic_when_model_fails(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("rewrite model unavailable"))

        with patch("reasoner.infrastructure.llm.registry.build_provider", return_value=mock_provider):
            rewritten = await _rewrite_prompt_for_policy_safety(
                "A whimsical Disney beach picnic with Mickey Mouse and Donald Duck",
                api_key="test-key",
            )

        assert rewritten is not None
        lowered = rewritten.lower()
        assert "disney" not in lowered
        assert "mickey mouse" not in lowered
        assert "donald duck" not in lowered


class TestGenerateImageWithModel:
    @pytest.fixture(autouse=True)
    def _patch_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    @pytest.mark.asyncio
    async def test_success_with_images_field_string(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = ["data:image/png;base64,abc123"]
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await generate_image_with_model("a cat", "gemini-flash-image")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,abc123"
        assert result["model_used"] == "gemini-flash-image"

    @pytest.mark.asyncio
    async def test_prefers_images_api_before_chat_for_image_models(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=AssertionError("chat path should not run"))

        mock_images_response = MagicMock()
        mock_images_response.data = [{"url": "https://files.example.com/generated-image"}]
        mock_client.images.generate = AsyncMock(return_value=mock_images_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
            "reasoner.infrastructure.llm.image_generation._download_image_url",
            new_callable=AsyncMock,
        ) as mock_download:
            mock_download.return_value = "data:image/png;base64,images-first"
            result = await generate_image_with_model("a cat", "gemini-flash-image")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,images-first"
        assert mock_client.images.generate.await_count == 1

    @pytest.mark.asyncio
    async def test_success_with_images_field_openrouter_format(self):
        """Test the OpenRouter image_url format."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = [{"image_url": {"url": "data:image/png;base64,openrouter123"}}]
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await generate_image_with_model("a cat", "gemini-flash-image")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,openrouter123"
        assert result["model_used"] == "gemini-flash-image"

    @pytest.mark.asyncio
    async def test_success_with_content_fallback(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = None
        # Use realistic base64 data (at least 100 chars to match regex)
        b64_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==" * 2
        mock_message.content = f"Here is your image: ![img](data:image/png;base64,{b64_data})"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await generate_image_with_model("a dog", "gemini-flash-image")

        assert result["success"] is True
        assert f"data:image/png;base64,{b64_data}" in result["image_data"]

    @pytest.mark.asyncio
    async def test_success_with_structured_content_parts(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = None
        mock_message.content = [
            {"type": "output_text", "text": "Generated image below."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,structured123"}},
        ]
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await generate_image_with_model("a robot", "gpt-5-image-mini")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,structured123"
        assert result["model_used"] == "gpt-5-image-mini"

    @pytest.mark.asyncio
    async def test_success_with_remote_image_url(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = [{"image_url": {"url": "https://cdn.example.com/generated?id=456"}}]
        mock_message.content = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
            "reasoner.infrastructure.llm.image_generation._download_image_url",
            new_callable=AsyncMock,
        ) as mock_download:
            mock_download.return_value = "data:image/png;base64,downloaded123"
            result = await generate_image_with_model("a robot", "gpt-5-image-mini")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,downloaded123"
        assert result["model_used"] == "gpt-5-image-mini"

    @pytest.mark.asyncio
    async def test_falls_back_to_images_api_after_text_only_chat_response(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = None
        mock_message.content = "Absolutely! That sounds like a wonderfully charming image. Here it is: https://files.example.com/generated"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_images_response = MagicMock()
        mock_images_response.data = [{"url": "https://files.example.com/generated-image"}]
        mock_client.images.generate = AsyncMock(return_value=mock_images_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client), patch(
            "reasoner.infrastructure.llm.image_generation._download_image_url",
            new_callable=AsyncMock,
        ) as mock_download:
            mock_download.side_effect = [
                None,
                "data:image/png;base64,from-images-api",
            ]
            result = await generate_image_with_model("a cat", "gemini-flash-image")

        assert result["success"] is True
        assert result["image_data"] == "data:image/png;base64,from-images-api"
        assert mock_client.images.generate.await_count == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_images_api_after_empty_choices(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_images_response = MagicMock()
        mock_images_response.data = [{"b64_json": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="}]
        mock_client.images.generate = AsyncMock(return_value=mock_images_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await generate_image_with_model("a cat", "gemini-flash-image")

        assert result["success"] is True
        assert result["image_data"].startswith("data:image/png;base64,")
        assert mock_client.images.generate.await_count == 1

    @pytest.mark.asyncio
    async def test_raises_on_empty_choices(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client.images.generate = AsyncMock(return_value=MagicMock(data=[]))

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(ImageGenerationError, match="Empty choices"):
                await generate_image_with_model("a cat", "gemini-flash-image")

    @pytest.mark.asyncio
    async def test_raises_on_no_images(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.images = None
        mock_message.content = "I cannot generate images."
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(ImageGenerationError, match="Could not extract image"):
                await generate_image_with_model("a cat", "gemini-flash-image")

    @pytest.mark.asyncio
    async def test_raises_on_api_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("Rate limited"))

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            with pytest.raises(ImageGenerationError, match="Rate limited"):
                await generate_image_with_model("a cat", "gemini-flash-image")


class TestGenerateImages:
    @pytest.fixture(autouse=True)
    def _patch_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    @pytest.mark.asyncio
    async def test_budget_preset_success(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = {
                "success": True,
                "image_data": "data:image/png;base64,ok",
                "model_used": "gemini-flash-image",
            }
            result = await generate_images("a cat", preset="budget", enhance=False, num_images=4)

        assert result["success"] is True
        assert len(result["images"]) == 4  # All 4 budget models return success
        assert result["images"][0]["image_data"] == "data:image/png;base64,ok"
        assert mock_gen.call_count == 4

    @pytest.mark.asyncio
    async def test_budget_preset_one_fails(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            call_count = 0
            def _side_effect(prompt, alias, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if alias == "seedream-4.5":
                    raise ImageGenerationError("Secondary failed")
                return {"success": True, "image_data": f"data:image/png;base64,ok{call_count}", "model_used": alias}
            mock_gen.side_effect = _side_effect
            result = await generate_images("a cat", preset="budget", enhance=False, num_images=3)

        assert result["success"] is True
        assert len(result["images"]) == 3
        # Derived from the constant rather than pinned: the budget primary list
        # has been re-ordered and resized twice since these numbers were written.
        # seedream-4.5 is a fallback, so the three primaries alone satisfy num_images=3.
        assert result["images"][0]["model_used"] == IMAGE_GEN_PRESETS["budget"][0]
        assert mock_gen.call_count == len(IMAGE_GEN_PRESETS["budget"])

    @pytest.mark.asyncio
    async def test_all_models_fail(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.side_effect = ImageGenerationError("All down")
            result = await generate_images("a cat", preset="budget", enhance=False)

        assert result["success"] is False
        assert "All models failed" in result["error"]

    @pytest.mark.asyncio
    async def test_fallback_model_used_after_primary_pair_fails(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            def _side_effect(prompt, alias, *args, **kwargs):
                if alias == "flux.2-pro":
                    return {"success": True, "image_data": "data:image/png;base64,fallback", "model_used": alias}
                raise ImageGenerationError(f"{alias} failed")
            mock_gen.side_effect = _side_effect
            result = await generate_images("a cat", preset="budget", enhance=False, num_images=4)

        assert result["success"] is False
        assert "Generated only 1 of 4 required images" in result["error"]
        # Every primary and every fallback is attempted before giving up.
        assert mock_gen.call_count == len(IMAGE_GEN_PRESETS["budget"]) + len(
            IMAGE_GEN_FALLBACKS["budget"]
        )

    @pytest.mark.asyncio
    async def test_partial_success_after_all_fallbacks_is_failure(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            def _side_effect(prompt, alias, *args, **kwargs):
                if alias == "riverflow-v2-fast-preview":
                    return {"success": True, "image_data": "data:image/png;base64,ok", "model_used": alias}
                raise ImageGenerationError(f"{alias} failed")
            mock_gen.side_effect = _side_effect
            result = await generate_images("a cat", preset="budget", enhance=False, num_images=4)

        assert result["success"] is False
        assert "Generated only 1 of 4 required images" in result["error"]
        # Every primary and every fallback is attempted before giving up.
        assert mock_gen.call_count == len(IMAGE_GEN_PRESETS["budget"]) + len(
            IMAGE_GEN_FALLBACKS["budget"]
        )

    @pytest.mark.asyncio
    async def test_policy_safe_prompt_retry_recovers_after_moderation_failures(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation._run_generation_attempts",
            new_callable=AsyncMock,
        ) as mock_attempts, patch(
            "reasoner.infrastructure.llm.image_generation._rewrite_prompt_for_policy_safety",
            new_callable=AsyncMock,
        ) as mock_rewrite:
            mock_attempts.side_effect = [
                (
                    [],
                    [
                        "gemini-flash-image: Could not extract image from gemini-flash-image response. Content preview: Here is your whimsical scene...",
                        "gpt-5-image-mini: No extractable image data or text from gpt-5-image-mini",
                        "flux.2-flex: API call failed for flux.2-flex: Request Moderated",
                    ],
                ),
                (
                    [
                        {"image_data": "data:image/png;base64,recovered", "model_used": "gemini-flash-image"},
                        {"image_data": "data:image/png;base64,recovered2", "model_used": "gpt-5-image-mini"},
                        {"image_data": "data:image/png;base64,recovered3", "model_used": "flux.2-flex"},
                        {"image_data": "data:image/png;base64,recovered4", "model_used": "riverflow-v2-fast"},
                    ],
                    [],
                ),
            ]
            mock_rewrite.return_value = "An original cheerful cartoon mouse and sailor duck enjoying a sunny beach picnic"

            result = await generate_images("Mickey Mouse and Donald Duck at the beach", preset="budget", enhance=False)

        assert result["success"] is True
        assert result["rewritten_prompt"] == "An original cheerful cartoon mouse and sailor duck enjoying a sunny beach picnic"
        assert len(result["images"]) == 4
        assert result["images"][0]["image_data"] == "data:image/png;base64,recovered"
        assert mock_attempts.await_count == 2
        mock_rewrite.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_policy_safe_prompt_retry_uses_heuristic_when_rewrite_model_fails(self):
        mock_provider = MagicMock()
        mock_provider.complete = AsyncMock(side_effect=RuntimeError("rewrite failed"))

        with patch(
            "reasoner.infrastructure.llm.image_generation._run_generation_attempts",
            new_callable=AsyncMock,
        ) as mock_attempts, patch(
            "reasoner.infrastructure.llm.registry.build_provider",
            return_value=mock_provider,
        ):
            mock_attempts.side_effect = [
                (
                    [],
                    [
                        "gemini-flash-image: Could not extract image from gemini-flash-image response. Content preview: Disney scene...",
                        "gpt-5-image-mini: No extractable image data or text from gpt-5-image-mini",
                        "flux.2-flex: API call failed for flux.2-flex: Request Moderated",
                    ],
                ),
                (
                    [
                        {"image_data": "data:image/png;base64,recovered", "model_used": "gemini-flash-image"},
                        {"image_data": "data:image/png;base64,recovered2", "model_used": "gpt-5-image-mini"},
                        {"image_data": "data:image/png;base64,recovered3", "model_used": "flux.2-flex"},
                        {"image_data": "data:image/png;base64,recovered4", "model_used": "riverflow-v2-fast"},
                    ],
                    [],
                ),
            ]

            result = await generate_images(
                "Disney beach picnic with Mickey Mouse and Donald Duck",
                preset="budget",
                enhance=False,
                api_key="test-key",
            )

        assert result["success"] is True
        assert result["rewritten_prompt"] is not None
        lowered = result["rewritten_prompt"].lower()
        assert "disney" not in lowered
        assert "mickey mouse" not in lowered
        assert "donald duck" not in lowered
        assert len(result["images"]) == 4
        assert mock_attempts.await_count == 2

    @pytest.mark.asyncio
    async def test_premium_preset_uses_correct_models(self):
        with patch(
            "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_gen.return_value = {
                "success": True,
                "image_data": "data:image/png;base64,premium",
                "model_used": "gemini-pro-image",
            }
            result = await generate_images("a cat", preset="premium", enhance=False)

        assert result["success"] is True
        # Both tiers ship IMAGE_GEN_IMAGE_COUNT primaries and must return that
        # many images; premium was a 2-model pair before the 4-model rework.
        assert len(result["images"]) == IMAGE_GEN_IMAGE_COUNT
        assert mock_gen.call_count == IMAGE_GEN_IMAGE_COUNT  # all primaries in parallel


class TestImageGenPresets:
    # Two drifts fixed here. PRESETS maps id -> raw config dict, so the typed
    # attribute reads need get_preset(). And primary_id on an image-gen preset
    # is the *reasoning* model that enhances the prompt -- the image model
    # lives under routing["image_generate"], which is what these tests meant.
    def test_budget_preset_exists(self):
        assert "image-gen-budget" in PRESETS
        p = get_preset("image-gen-budget")
        assert p.routing["image_generate"] == "gemini-3.1-flash-lite-image"

    def test_premium_preset_exists(self):
        assert "image-gen-premium" in PRESETS
        p = get_preset("image-gen-premium")
        assert p.routing["image_generate"] == "gemini-pro-image"
