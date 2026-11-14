"""DegradedLLMResponse: what ProviderRouter returns when every provider fails.

No exceptions and no provider base class live here: the one base is
base.BaseLLMProvider and the error vocabulary is core.exceptions (P2,
docs/plans/root-cause-remediation-2026-09-07.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DegradedLLMResponse:
    """
    Placeholder response when all LLM providers fail.
    
    Carries enough metadata for downstream telemetry and UI warnings.
    """
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    degraded: bool = True
    error: str = ""

    def __bool__(self) -> bool:
        """Always false: this object is a failure, and must not read as success.

        ``router.call`` returns ``tuple[str | DegradedLLMResponse, dict]``, so a
        caller cannot tell the two apart without an explicit ``isinstance``
        check. The production path does check (``LLMExecutor`` at both call
        sites, plus headless, main, HyperGate and the subagent base), but a
        dataclass instance is truthy by default, so any *new* caller written as
        ``if not response:`` silently treats a total provider failure as a
        successful reply.

        Not hypothetical: the e2e suite's
        ``test_all_presets_can_make_real_call`` does exactly that. Its
        ``assert response`` passed on a degraded object and it failed one line
        later on empty metadata, which reads like a metadata bug rather than
        the empty completion it actually was.

        Returning False makes the naive spelling correct instead of wrong.
        Explicit ``isinstance`` checks are unaffected.
        """
        return False

    @property
    def tokens_total(self) -> int:
        """Total tokens used."""
        return self.metadata.get("input_tokens", 0) + self.metadata.get("output_tokens", 0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.text,
            'model_used': self.metadata.get("model", "unknown"),
            'tokens': {
                'prompt': self.metadata.get("input_tokens", 0),
                'completion': self.metadata.get("output_tokens", 0),
                'total': self.tokens_total,
            },
            'finish_reason': self.metadata.get("finish_reason", "error"),
            'metadata': self.metadata,
        }

