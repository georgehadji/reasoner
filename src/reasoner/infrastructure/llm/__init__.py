# LLM Adapters (legacy direct-provider adapters removed — all routing goes through OpenRouter)
#
# One provider base class and one error tree, since P2
# (docs/plans/root-cause-remediation-2026-09-07.md):
#
#     base.BaseLLMProvider          complete(system_prompt, user_prompt, ...) -> str
#     core.exceptions.ProviderError caught by ProviderRouter._execute_call
#
# base.LLMError is the residual leaf of that tree, for failures an adapter
# could not classify further; everything else is translated at the adapter
# boundary (providers/openai_compat.py::_translate, providers/direct.py::
# _translate).
#
# This package used to hold a second BaseLLMProvider in ports.py with an
# incompatible interface and no complete_with_retry(), plus three more LLMError
# classes in ports.py, exceptions.py and base.py, none a subclass of the
# others. Both traps had been sprung: NoopProvider and two dummy providers
# subclassed the ports base, and an infrastructure LLMError raised from a
# provider was not caught by the fallback chain. The duplicates are deleted;
# infrastructure/llm/exceptions.py is a deprecated alias shim.
#
# LLMConfig, LLMResponse and Message below are the data types ports.py still
# owns; import them from .ports when writing to the LLMProvider Protocol.

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
