"""Strategy interface for building per-language container invocations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from reasoner.core.ports.code_executor import ExecutionLimits


@dataclass(frozen=True)
class ContainerRunSpec:
    """Everything needed to launch one job container.

    Built entirely server-side by a ``LanguageRunner`` from a fixed image
    and argv — callers of the sandbox worker never supply an image,
    command, mount, or environment variable directly. ``argv`` is a list
    (never a shell string) so it reaches ``docker run`` without any shell
    interpolation.
    """
    image: str
    argv: list[str] = field(default_factory=list)
    stdin_payload: str = ""


@runtime_checkable
class LanguageRunner(Protocol):
    """Adapter that knows how to run one language inside the sandbox image."""

    language: str

    def build_command(self, code: str, stdin: str, limits: ExecutionLimits) -> ContainerRunSpec:
        """Build the fixed container invocation for this piece of code.

        ``code`` must never appear as a shell-interpolated string — encode
        it into the argv/stdin payload so it can't be interpreted as extra
        flags or shell syntax by the container runtime.
        """
        ...
