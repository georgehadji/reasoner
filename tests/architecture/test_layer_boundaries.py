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
from pathlib import Path

import pytest

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
    # core/degrade.py: lazy inline import of the Prometheus counter inside
    # degraded(), for the same reason as core/search.py above -- the metric is
    # an optional dependency and must not be a module-scope core->infra edge.
    "core/degrade.py": ["reasoner.infrastructure.metrics"],

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
    assert lines <= 1110, f"api/__init__.py is {lines} lines (pinned cap: 1110)"


def test_models_size() -> None:
    """models.py should not grow past its pinned cap. Target: <300 lines."""
    path = BASE / "models.py"
    if not path.exists():
        pytest.skip("models.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 62, f"models.py is {lines} lines (pinned cap: 62)"


def test_streaming_size() -> None:
    """api/streaming.py should not grow past its pinned cap. Target: <400 lines."""
    path = BASE / "api" / "streaming.py"
    if not path.exists():
        pytest.skip("api/streaming.py not found")
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= 337, f"api/streaming.py is {lines} lines (pinned cap: 337)"


# ─────────────────────────────────────────────────────────────────────
# P2: the domain owns the error vocabulary
# ─────────────────────────────────────────────────────────────────────
#
# docs/plans/root-cause-remediation-2026-09-07.md P2 step 6 asks for an
# import-linter contract forbidding `class .*Error` under infrastructure/.
# import-linter reasons about imports between modules; it has no notion of a
# class definition, so it cannot express this. An AST sweep can, and it runs in
# the normal suite instead of needing new CI wiring.
#
# Why the rule: infrastructure/llm/ grew four unrelated exception trees, each
# added by someone who did not find the previous one. Two of them were outside
# the type ProviderRouter caught, so those failures walked past the fallback
# chain; one declared `.retryable` that `core.exceptions.is_retryable` never
# read, because it read `.retryable` on ReasonerError subclasses only. Adapters
# translate into the domain's vocabulary at the boundary; they do not mint
# their own.

# Exact set, ratchet-style: a new entry fails this test, and deleting one means
# deleting its line. Every entry is pre-existing debt with a stated reason.
ALLOWED_INFRASTRUCTURE_ERRORS: dict[str, str] = {
    # The residual "adapter could not classify this any further" case. Now a
    # core.exceptions.ProviderError subclass, so it is inside the tree the
    # router catches. Scheduled to move into core/ with the compat aliases.
    "infrastructure/llm/base.py::LLMError":
        "residual ProviderError; moves to core/ when the aliases are deleted",
    # Raised by the NoopProvider when it is used in a path that needed a real
    # model. A configuration fault, not a provider fault.
    "infrastructure/llm/providers/noop.py::NoopProviderError":
        "no-API-key sentinel; subclasses LLMError",
    # Control-flow signal for the breaker, not a provider failure: it means the
    # call was never attempted.
    "infrastructure/circuit_breaker.py::CircuitOpenError":
        "breaker control flow; predates the port split",
    # Legacy auth adapter, superseded by api/auth_deps.py.
    "infrastructure/auth_legacy.py::AuthenticationError":
        "legacy adapter, scheduled for deletion",
    "infrastructure/auth_legacy.py::AuthorizationError":
        "legacy adapter, scheduled for deletion",
    # Non-LLM adapters with no domain vocabulary to translate into yet.
    "infrastructure/llm/image_generation.py::ImageGenerationError":
        "image lane has no domain error tree yet",
    "infrastructure/watermark/data_url.py::DataUrlError":
        "ValueError subclass, local input validation",
    "infrastructure/widgets_legacy.py::SafeExpressionError":
        "legacy widget sandbox, scheduled for deletion",
    # Defined only in the ImportError branch, as a stand-in for
    # asyncpg.PostgresError when asyncpg is absent. Without it the `except`
    # clauses would have to name bare Exception and would swallow KeyError,
    # TypeError and ValueError from the same try blocks.
    "infrastructure/persistence/postgres_store.py::_AsyncpgError":
        "optional-dependency sentinel; narrows an except clause, never raised",
}


def _infrastructure_error_classes() -> dict[str, str]:
    """Every `class *Error`/`*Exception` defined under infrastructure/."""
    found: dict[str, str] = {}
    for path in sorted((BASE / "infrastructure").rglob("*.py")):
        rel = path.relative_to(BASE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and (
                node.name.endswith("Error") or node.name.endswith("Exception")
            ):
                found[f"{rel}::{node.name}"] = node.name
    return found


def test_infrastructure_defines_no_new_exception_classes():
    """Adapters translate into core.exceptions; they do not define errors."""
    found = _infrastructure_error_classes()

    new = sorted(set(found) - set(ALLOWED_INFRASTRUCTURE_ERRORS))
    assert not new, (
        "New exception class(es) defined under infrastructure/:\n  "
        + "\n  ".join(new)
        + "\n\nRaise a subclass of reasoner.core.exceptions.ProviderError (or the "
        "appropriate domain error) instead, translated at the adapter boundary — "
        "see providers/openai_compat.py::_translate. If this genuinely cannot be "
        "a domain error, add it to ALLOWED_INFRASTRUCTURE_ERRORS with the reason."
    )

    gone = sorted(set(ALLOWED_INFRASTRUCTURE_ERRORS) - set(found))
    assert not gone, (
        "Allowlisted infrastructure error(s) no longer exist — delete these "
        f"lines from ALLOWED_INFRASTRUCTURE_ERRORS: {gone}"
    )


def test_every_provider_facing_error_is_reachable_from_provider_error():
    """The router catches ProviderError; adapters must raise inside that tree.

    LLMError and NoopProviderError are the two error classes an adapter can
    still raise. Both must be ProviderError subclasses or the fallback chain
    does not fire for them.
    """
    from reasoner.core.exceptions import ProviderError
    from reasoner.infrastructure.llm.base import LLMError
    from reasoner.infrastructure.llm.providers.noop import NoopProviderError

    assert issubclass(LLMError, ProviderError)
    assert issubclass(NoopProviderError, ProviderError)
