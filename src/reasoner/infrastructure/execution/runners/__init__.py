"""Language-runner strategy registry for the container sandbox.

Each ``LanguageRunner`` builds the fixed image/argv for one language. The
sandbox worker never accepts an image, command, or mount from a caller —
those come only from a registered runner.
"""

from __future__ import annotations

from reasoner.infrastructure.execution.runners.base import ContainerRunSpec, LanguageRunner
from reasoner.infrastructure.execution.runners.python_runner import PythonRunner

_RUNNERS: dict[str, LanguageRunner] = {
    "python": PythonRunner(),
}


def get_runner(language: str) -> LanguageRunner:
    """Look up the runner for a language, raising on anything unregistered.

    Fail closed: an unknown language must never fall back to a default
    runner and silently execute as Python.
    """
    try:
        return _RUNNERS[language]
    except KeyError:
        raise ValueError(f"No sandbox runner registered for language: {language!r}") from None


__all__ = ["ContainerRunSpec", "LanguageRunner", "PythonRunner", "get_runner"]
