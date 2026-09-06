# LLM Adapters (legacy direct-provider adapters removed — all routing goes through OpenRouter)
#
# This package holds two unrelated provider interfaces, and the names collide.
# What is exported here is the pair ProviderRouter and the registry deal in:
#
#     base.BaseLLMProvider   complete(system_prompt, user_prompt, ...) -> str
#     base.LLMError          caught by ProviderRouter._execute_call
#
# The other pair lives in ports.py and is a different interface, not a
# subclass:
#
#     ports.BaseLLMProvider     complete(messages, config) -> LLMResponse
#     exceptions.LLMError       InfrastructureError, NOT a base.LLMError
#
# Exporting the ports/exceptions ones from here was a trap. A provider built
# on ports.BaseLLMProvider has no complete_with_retry(), so a router holding
# one raises AttributeError on its first call; and an exceptions.LLMError
# raised from a provider is not caught by the fallback chain, which is the
# same defect as the raw SDK exceptions fixed in 4af087e. Both traps had
# already been sprung: NoopProvider and two dummy providers subclassed the
# ports one.
#
# LLMConfig, LLMResponse and Message below belong to the ports interface and
# have no base equivalent; import them from .ports when writing to it.

from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.infrastructure.llm.ports import LLMConfig, LLMResponse, Message

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "LLMConfig",
    "Message",
    "LLMError",
    "LLMExecutor",
]
