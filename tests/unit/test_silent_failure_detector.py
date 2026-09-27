"""What scripts/silent_failure_ratchet.py counts, and what it deliberately does not.

The ratchet is exact-equality in both directions, so its MAX is only as
meaningful as its detector. It ran for weeks on a line regex that could not see
``infrastructure/llm/executor.py:756`` — a handler whose whole body is
``logger.debug(..., exc_info=True)`` wrapping spend-cap enforcement — and the
number stayed green the entire time
(docs/plans/implementation_audit_report.md, C-1 and H-1).

These tests pin the four shapes on each side of the line, so a future
"simplification" of the detector fails here rather than by quietly lowering a
number nobody re-derives.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "silent_failure_ratchet.py"


def _load_ratchet():
    spec = importlib.util.spec_from_file_location("silent_failure_ratchet", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("silent_failure_ratchet", module)
    spec.loader.exec_module(module)
    return module


ratchet = _load_ratchet()


def _sites(tmp_path: Path, body: str) -> list[int]:
    """Line numbers the detector flags in a one-file tree."""
    (tmp_path / "sample.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return [lineno for _, lineno in ratchet.find_swallow_sites(tmp_path)]


COUNTED = {
    "bare pass": """
        def f():
            try:
                g()
            except Exception:
                pass
    """,
    "bare return": """
        def f():
            try:
                return g()
            except Exception:
                return []
    """,
    # D11's shape. The only trace is at a level nobody alerts on, and the
    # caller receives a value indistinguishable from a real empty result.
    "quiet log, then return": """
        import logging
        logger = logging.getLogger(__name__)

        def f():
            try:
                return g()
            except Exception as exc:
                logger.debug("g failed: %s", exc)
                return []
    """,
    # Same, minus the return: the handler falls through and the function
    # returns None, which is a value the caller will use.
    "quiet log, fall through": """
        import logging
        logger = logging.getLogger(__name__)

        def f():
            try:
                g()
            except Exception:
                logger.debug("g failed", exc_info=True)
    """,
    # The regex required Exception as the first token after `except`.
    "Exception inside a tuple": """
        def f():
            try:
                g()
            except (ValueError, Exception):
                pass
    """,
    # The regex read the handler body from the *next* line.
    "handler body on the except line": """
        def f():
            try:
                return g()
            except Exception: return []
    """,
}

NOT_COUNTED = {
    # WARNING and above is the line the contract draws: a trace someone alerts on.
    "warning, fall through": """
        import logging
        logger = logging.getLogger(__name__)

        def f():
            try:
                g()
            except Exception:
                logger.warning("g failed", exc_info=True)
    """,
    "exception-level log": """
        import logging
        logger = logging.getLogger(__name__)

        def f():
            try:
                g()
            except Exception:
                logger.exception("g failed")
                return []
    """,
    "re-raises": """
        import logging
        logger = logging.getLogger(__name__)

        def f():
            try:
                g()
            except Exception:
                logger.debug("g failed")
                raise
    """,
    # The sanctioned conversion. Without this exemption the ratchet would
    # punish the fix it exists to drive.
    "routed through degraded()": """
        from reasoner.core.degrade import degraded

        def f(state):
            try:
                return g()
            except Exception as exc:
                return degraded("sample.site", [], exc=exc, state=state)
    """,
    # A handler that does real recovery work is not a swallow, whatever it
    # logs. Only pass/return/quiet-log bodies qualify.
    "does recovery work": """
        import logging
        logger = logging.getLogger(__name__)

        def f(self):
            try:
                g()
            except Exception:
                logger.debug("falling back")
                self._fallback()
    """,
    # `except:` with no type is a rarer, separate shape. Folding it in would
    # move the number for a reason unrelated to the contract being measured.
    "bare except with no type": """
        def f():
            try:
                g()
            except:
                pass
    """,
}


@pytest.mark.parametrize("shape", sorted(COUNTED), ids=sorted(COUNTED))
def test_counted_shapes(tmp_path, shape):
    assert _sites(tmp_path, COUNTED[shape]) != [], f"{shape!r} should count as a silent failure"


@pytest.mark.parametrize("shape", sorted(NOT_COUNTED), ids=sorted(NOT_COUNTED))
def test_uncounted_shapes(tmp_path, shape):
    assert _sites(tmp_path, NOT_COUNTED[shape]) == [], f"{shape!r} must not count"


def test_docstrings_are_not_counted(tmp_path):
    """core/degrade.py documents the pattern this script asks callers to adopt.

    Under the old text scan that docstring counted as a site, so documenting
    the fix raised the number the fix is supposed to lower. Parsing makes the
    exemption structural instead of a line-range guard.
    """
    assert _sites(
        tmp_path,
        '''
        def f():
            """Convert a swallow like this one::

                except Exception:
                    pass
            """
            return 1
    ''',
    ) == []


def test_a_site_is_reported_at_the_except_line(tmp_path):
    """The printed line number is the handler, not its body.

    Every MAX-bump commit message cites these as file:line; pointing them one
    line off makes that provenance useless.
    """
    assert _sites(
        tmp_path,
        """
        def f():
            try:
                g()
            except Exception:
                pass
    """,
    ) == [5]
