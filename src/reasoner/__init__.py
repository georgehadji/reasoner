"""
Reasoner — AI Reasoning Platform.

Install secret redaction at the package level so ALL entry points
(API, CLI, tests) get it — not just the FastAPI app path.
"""
from __future__ import annotations

__version__ = "2.1.0"

# Runs when `import reasoner` is executed — before any submodule produces log
# output — so API keys, tokens, and connection strings are redacted everywhere.
#
# This previously did `logging.getLogger().addFilter(SafeLoggingFilter())`.
# A filter on the root *logger* only runs for records that logger itself
# creates; records from `logging.getLogger(__name__)` reach root's handlers
# without ever running root's filters. Every module in this package uses a
# named logger, so redaction covered essentially nothing. Wrapping the record
# factory (in install_global_redaction) cannot be bypassed that way, and also
# covers handlers added later (e.g. by uvicorn/gunicorn).
from reasoner.core.logging_utils import install_global_redaction

install_global_redaction()
