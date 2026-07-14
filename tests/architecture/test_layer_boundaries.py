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
    """Extract all 'from reasoner.X import' statements from a Python file.

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


@pytest.mark.xfail(reason="Target: <250 lines. Refactoring in progress (Phase 1.3)")
def test_api_init_size() -> None:
    """api/__init__.py should be under 250 lines."""
    path = BASE / "api" / "__init__.py"
    if not path.exists():
        pytest.skip("api/__init__.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines < 250, f"api/__init__.py is {lines} lines (limit: 250)"


@pytest.mark.xfail(reason="Target: <300 lines. models.py now a 49-line shim (Phase 2.1)")
def test_models_size() -> None:
    """models.py should be under 300 lines."""
    path = BASE / "models.py"
    if not path.exists():
        pytest.skip("models.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines < 300, f"models.py is {lines} lines (limit: 300)"


@pytest.mark.xfail(reason="Target: <400 lines. Refactoring in progress")
def test_streaming_size() -> None:
    """api/streaming.py should be under 400 lines."""
    path = BASE / "api" / "streaming.py"
    if not path.exists():
        pytest.skip("api/streaming.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines < 400, f"api/streaming.py is {lines} lines (limit: 400)"
