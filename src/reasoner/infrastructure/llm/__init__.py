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
# A second BaseLLMProvider and three more LLMError trees used to live here;
# P2 deleted them (tests/test_defect_hunt_fixes.py guards the result).

from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError
from reasoner.infrastructure.llm.executor import LLMExecutor

__all__ = [
    "BaseLLMProvider",
    "LLMError",
    "LLMExecutor",
]
