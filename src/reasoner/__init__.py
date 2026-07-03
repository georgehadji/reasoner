"""
Reasoner — AI Reasoning Platform.

Wire SafeLoggingFilter at the package level so ALL entry points
(API, CLI, tests) get secret redaction in their logs — not just
the FastAPI app path.
"""
from __future__ import annotations
import logging

__version__ = "2.1.0"

# Install SafeLoggingFilter on root logger at import time.
# This runs when `import reasoner` is executed — before any submodule
# produces log output, ensuring API keys, tokens, and secrets are
# redacted from every log handler.
from reasoner.core.logging_utils import SafeLoggingFilter

logging.getLogger().addFilter(SafeLoggingFilter())
