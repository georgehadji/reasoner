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
# named logger, so redaction covered essentially nothing — verified by
# emitting a live-format key through a child logger and seeing it in full.
# Wrapping the record factory cannot be bypassed that way.
from reasoner.core.logging_utils import install_global_redaction

install_global_redaction()
