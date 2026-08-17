"""Python language runner — the only concrete LanguageRunner today.

Code is base64-encoded into the argv (never interpolated as a shell
string, never written to a bind-mounted file) so the container's real
stdin channel stays free for the program's own input.
"""

from __future__ import annotations

import base64

from reasoner.core.ports.code_executor import ExecutionLimits
from reasoner.infrastructure.execution.runners.base import ContainerRunSpec

# Built by infrastructure/execution/sandbox_worker/sandbox_image/Dockerfile.
PYTHON_SANDBOX_IMAGE = "reasoner-sandbox-python:latest"


class PythonRunner:
    """Builds the container invocation for Python code."""

    language = "python"

    def build_command(self, code: str, stdin: str, limits: ExecutionLimits) -> ContainerRunSpec:
        encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
        launcher = (
            "import base64,sys;"
            f"_src=base64.b64decode('{encoded}').decode('utf-8');"
            "exec(compile(_src, '<sandbox>', 'exec'))"
        )
        return ContainerRunSpec(
            image=PYTHON_SANDBOX_IMAGE,
            # -I: isolated mode (ignore env/user site-packages).
            # -S: skip site module (faster start, smaller attack surface).
            argv=["python3", "-I", "-S", "-c", launcher],
            stdin_payload=stdin,
        )
