"""A HyperGate sub-agent must report the provider's failure, not a parse crash.

``router.call`` returns ``(text | DegradedLLMResponse, meta)``. The sub-agent
used to run its ``isinstance`` check on the whole tuple, which never matches,
so the degraded object reached ``_parse_result`` and surfaced as
``TypeError: expected string or bytes-like object`` instead of the real error.
"""

from __future__ import annotations

import asyncio
from typing import Any

from reasoner.hypergate.base_sub_agent import BaseSubAgent
from reasoner.hypergate.models import SubAgentInput
from reasoner.infrastructure.llm.ports import DegradedLLMResponse


class _Agent(BaseSubAgent):
    AGENT_NAME = "degraded_probe"
    parsed: list[Any]

    def _system_prompt(self) -> str:
        return "classify"

    def _parse_result(self, raw: str) -> dict[str, Any]:
        self.parsed.append(raw)
        return {"confidence": 1.0}


class _Router:
    async def call(self, **_: Any) -> tuple[Any, dict[str, Any]]:
        return DegradedLLMResponse(error="all providers failed: timeout"), {}


def test_degraded_response_reports_provider_error_without_parsing() -> None:
    agent = _Agent()
    agent.parsed = []
    out = asyncio.run(agent.execute(SubAgentInput(problem="x", agent_name="t"), _Router()))  # type: ignore[arg-type]

    assert agent.parsed == []
    assert out.confidence == 0.0
    assert out.error == "all providers failed: timeout"
