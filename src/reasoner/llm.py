"""
Reasoner Pipeline — Multi-Provider LLM Abstraction
Backward-compatible shim.  All implementations have moved to
reasoner.infrastructure.llm submodules.
"""

from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError
from reasoner.infrastructure.llm.providers.openai_compat import (
    OpenAICompatibleProvider,
    OpenRouterProvider,
)
from reasoner.infrastructure.llm.registry import (
    _MODEL_WHITELIST,
    _REGISTRY,
    build_provider,
    list_models,
)
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.llm.utils import (
    _patch_openai_platform_detection,
    _requests_strict_json,
    _perplexity_response_format,
)

__all__ = [
    "BaseLLMProvider",
    "LLMError",
    "OpenAICompatibleProvider",
    "OpenRouterProvider",
    "_MODEL_WHITELIST",
    "_REGISTRY",
    "build_provider",
    "list_models",
    "ProviderRouter",
    "_patch_openai_platform_detection",
    "_requests_strict_json",
    "_perplexity_response_format",
]
