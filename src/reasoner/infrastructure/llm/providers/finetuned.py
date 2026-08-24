"""
Fine-Tuned Model Provider

Adapter for custom fine-tuned models hosted on OpenAI, Together AI,
or any OpenAI-compatible custom endpoint.

This is a *framework* addition — it enables routing specific roles to
cheaper/faster fine-tuned models without changing the rest of the pipeline.

Usage:
    1. Register a fine-tuned model in registry.py:
       _FINE_TUNED_MODELS = {
           "ft-classifier-v1": {
               "provider": "finetuned",
               "base_url": "https://api.openai.com/v1",
               "model": "ft:gpt-4o-mini:reasoner:classifier:abc123",
           },
       }

    2. Map roles to fine-tuned models in the preset:
       fine_tuned_roles = {"classification": "ft-classifier-v1"}

    3. ProviderRouter.get("classification") returns the FineTunedProvider.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from reasoner.core.constants import DEFAULT_MAX_RETRIES
from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class FineTunedProvider(OpenAICompatibleProvider):
    """Provider for fine-tuned models on custom endpoints.

    Inherits all retry, streaming, and error-handling behavior from
    OpenAICompatibleProvider. The only difference is the base_url
    (pointing to the fine-tuned hosting endpoint) and the model ID
    (which is the fine-tuned model identifier).
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        from reasoner.core.settings import settings
        # Resolve API key: explicit > settings > env > None (OpenAI client will error clearly)
        resolved_key = (
            api_key
            or settings.OPENAI_API_KEY
            or settings.FINE_TUNED_API_KEY
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("FINE_TUNED_API_KEY")
        )
        super().__init__(
            model=model,
            api_key=resolved_key,
            base_url=base_url,
            max_retries=max_retries,
            extra_body=extra_body,
        )
        self._base_url = base_url
        logger.info(
            "FineTunedProvider initialized for model=%s at base_url=%s",
            model,
            base_url,
        )

    @property
    def provider_name(self) -> str:
        return f"finetuned:{self._base_url}"
