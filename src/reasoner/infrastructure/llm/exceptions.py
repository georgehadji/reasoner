"""Deprecated: the LLM error taxonomy now lives in ``reasoner.core.exceptions``.

P2, docs/plans/root-cause-remediation-2026-09-07.md. This module was the second
of four unrelated exception trees in one adapter layer. Its ``LLMError``
descended from ``InfrastructureError(Exception)``, so it was not a
``ReasonerError``: ``core.exceptions.is_retryable`` never consulted the
``.retryable`` these classes declared, and ``ProviderRouter`` never caught them.

The domain owns the error vocabulary; adapters translate into it at the
boundary (``providers/openai_compat.py::_translate``,
``providers/direct.py::_translate``). Every name below is now an alias for the
domain class of the same meaning, kept for one release. Import from
``reasoner.core.exceptions`` instead.

``SearchError`` and ``MemoryError`` are gone rather than aliased: nothing ever
imported them, and the second shadowed a builtin.
"""

from __future__ import annotations

import warnings

from reasoner.core.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderCreditsExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    ReasonerError,
    is_retryable,
)
from reasoner.infrastructure.llm.base import LLMError

warnings.warn(
    "reasoner.infrastructure.llm.exceptions is deprecated; import from "
    "reasoner.core.exceptions instead.",
    DeprecationWarning,
    stacklevel=2,
)

# InfrastructureError had exactly one role: a base for LLMError. The domain
# base takes that role now.
InfrastructureError = ReasonerError

__all__ = [
    "AuthenticationError",
    "InfrastructureError",
    "LLMError",
    "ModelNotFoundError",
    "ProviderCreditsExhaustedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "RateLimitError",
    "is_retryable",
]
