"""Architectural fitness functions — enforce dependency direction.

Layer rules:
  core/    -> must NOT import from infrastructure/, api/, or application/
  domain/  -> must NOT import from infrastructure/ or api/
  application/ -> must NOT import from api/
  api/     -> can import from anywhere (it's the outermost layer)
  infrastructure/ -> must NOT import from api/ (leaf layer)

Known exceptions tracked in ALLOWED_LINEAGE (TYPE_CHECKING guards, port adapters).
"""

from __future__ import annotations

import ast
import pytest
from pathlib import Path

BASE = Path("src/reasoner")

# Known allowed violations — imports under TYPE_CHECKING guard or port adapter patterns
# Each entry maps "relative/file.py" -> list of allowed import prefixes
ALLOWED_LINEAGE: dict[str, list[str]] = {
    # core/search.py: lazy inline imports inside functions (not module-level)
    "core/search.py": [
        "reasoner.infrastructure.llm.registry",
        "reasoner.infrastructure.circuit_breaker",
    ],
    # infrastructure/server_check.py: lazy inline import of api app for health check
    "infrastructure/server_check.py": [
        "reasoner.api",
    ],
    "core/protocol.py": ["reasoner.infrastructure.llm.router"],

    # application/handlers/handlers.py:263 — `import reasoner.api as api`, lazy
    # inside a function. Tracked upward-dependency debt, mirrored in
    # .importlinter's ignore_imports (application.handlers.handlers -> api).
    # Fix is Phase 3.2 of architecture-score-9-remediation-plan.md: invert via
    # an injected port. Do not add new entries here without a matching Phase 3
    # tracking item — this dict is a debt ledger, not a blanket exemption.
    "application/handlers/handlers.py": ["reasoner.api"],

    # orchestrator has lazy inline imports of api/clients (neuro fallback)
    # websocket manager imports api/history for run owner tracking
    # application/flows/*.py import from api.serializers shim (content moved to
    # application/services/serializers. TODO: update imports to new path)
}

FORBIDDEN_IMPORTS: dict[str, list[str]] = {
    "core": [
        "reasoner.infrastructure",
        "reasoner.api",
        "reasoner.application",
    ],
    "domain": [
        "reasoner.infrastructure",
        "reasoner.api",
    ],
    "application": [
        "reasoner.api",
    ],
    "infrastructure": [
        "reasoner.api",
    ],
}


def get_imports(file_path: Path) -> list[str]:
    """Extract all 'reasoner.X' module references from a Python file's imports.

    Covers both `from reasoner.x import y` (ImportFrom) and plain
    `import reasoner.x` (Import) — a bare `import reasoner.api` previously
    defeated this check entirely since only ImportFrom was walked.
    Does NOT skip TYPE_CHECKING imports (they are still real imports at parse time).
    Uses ALLOWED_LINEAGE to exempt known-safe TYPE_CHECKING and port adapter imports.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
    return imports


def _is_allowed(rel: str, imp: str) -> bool:
    """Check if this file:import combination is in the allowed violations list."""
    file_allowed = ALLOWED_LINEAGE.get(rel, [])
    return any(imp.startswith(a) for a in file_allowed)


@pytest.mark.parametrize("layer,forbidden_prefixes", FORBIDDEN_IMPORTS.items())
def test_layer_boundaries(layer: str, forbidden_prefixes: list[str]) -> None:
    """Verify no file in {layer}/ imports from forbidden modules."""
    layer_dir = BASE / layer
    if not layer_dir.exists():
        pytest.skip(f"Layer directory not found: {layer_dir}")

    violations: list[str] = []
    for py_file in sorted(layer_dir.rglob("*.py")):
        if py_file.name == "__init__.py" and py_file.parent == layer_dir:
            continue
        rel = str(py_file.relative_to(BASE)).replace("\\", "/")
        for imp in get_imports(py_file):
            if any(imp.startswith(prefix) for prefix in forbidden_prefixes):
                if not _is_allowed(rel, imp):
                    violations.append(f"  {rel} -> imports {imp}")

    assert not violations, (
        f"Layer boundary violations in {layer}/:\n" + "\n".join(violations)
    )


def test_no_circular_imports() -> None:
    """Verify top-level packages import cleanly without circular deps."""
    packages = [
        "reasoner.core",
        "reasoner.domain",
        "reasoner.application",
        "reasoner.infrastructure",
    ]
    import importlib
    errors = []
    for pkg in packages:
        try:
            importlib.import_module(pkg)
        except ImportError as exc:
            errors.append(f"Cannot import {pkg}: {exc}")
    assert not errors, (
        "Circular or broken imports detected:\n" + "\n".join(errors)
    )


# Real ratchet caps, pinned at the line count measured when this cap was
# introduced (architecture-score-9-remediation-plan.md, Phase 0.5). The
# xfail versions of these tests never failed AND never passed — xfail_strict
# was inert (see Phase 0.3), so growth went undetected either way. Aspirational
# targets (250/300/400 — see Phase 5) stay as comments; ratchet the pinned cap
# down as god modules in Phase 5 are decomposed. Do not raise a cap without
# shrinking the corresponding module first.

def test_api_init_size() -> None:
    """api/__init__.py should not grow past its pinned cap. Target: <250 lines (Phase 5.1)."""
    path = BASE / "api" / "__init__.py"
    if not path.exists():
        pytest.skip("api/__init__.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 1008, f"api/__init__.py is {lines} lines (pinned cap: 1008)"


def test_models_size() -> None:
    """models.py should not grow past its pinned cap. Target: <300 lines."""
    path = BASE / "models.py"
    if not path.exists():
        pytest.skip("models.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 59, f"models.py is {lines} lines (pinned cap: 59)"


def test_streaming_size() -> None:
    """api/streaming.py should not grow past its pinned cap. Target: <400 lines."""
    path = BASE / "api" / "streaming.py"
    if not path.exists():
        pytest.skip("api/streaming.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 337, f"api/streaming.py is {lines} lines (pinned cap: 337)"
