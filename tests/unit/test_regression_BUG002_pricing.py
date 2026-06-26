"""
Regression test for BUG-002: Pricing module silent failure.

_load_openrouter_pricing() previously swallowed all exceptions with
'except Exception: pass', making corrupt or missing pricing files
impossible to diagnose in production.
"""

import logging
from unittest.mock import patch, mock_open
# Canonical module: the `reasoner.pricing` shim re-exports via `import *`, which
# does not expose underscore-prefixed names. Import the private helper directly.
from reasoner.domain.pricing import _load_openrouter_pricing


def test_pricing_logs_error_on_corrupt_json(caplog):
    """
    If openrouter_models.json is corrupt, _load_openrouter_pricing
    must emit a WARNING log so operators can diagnose the issue.
    It must still return an empty dict safely (fallback to default
    pricing is preserved).
    """
    corrupt_json = "{not valid json"

    with patch("pathlib.Path.exists", return_value=True):
        with patch("pathlib.Path.open", mock_open(read_data=corrupt_json)):
            with caplog.at_level(logging.WARNING):
                result = _load_openrouter_pricing()

    assert "Failed to load pricing" in caplog.text
    assert isinstance(result, dict)
    assert len(result) == 0


def test_pricing_logs_error_on_missing_file(caplog):
    """A missing file should also produce a warning (OSError from open)."""
    with patch("pathlib.Path.exists", return_value=True):
        with patch("pathlib.Path.open", side_effect=OSError("no such file")):
            with caplog.at_level(logging.WARNING):
                result = _load_openrouter_pricing()

    assert "Failed to load pricing" in caplog.text
    assert result == {}
