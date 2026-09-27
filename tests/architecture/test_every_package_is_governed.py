"""A directory without `__init__.py` is invisible to every architecture gate.

PEP 420 namespace packages import fine at runtime, so nothing ever complained.
But grimp -- and therefore import-linter, and therefore the Layered Architecture
contract and its exception ratchet -- only walks regular packages. Ten
directories under `src/reasoner` had no `__init__.py`, so 52 modules were
outside the contract entirely:

    api/execution (5)   api/routes (21)   healing (5)
    infrastructure/redis (3)   infrastructure/search (3)
    core/observability   documents   infrastructure/email
    infrastructure/observability   utils

`lint-imports` reported "Analyzed 489 files" while the tree held 541. The gate
was green partly because it was not looking. Adding the ten files took the
count to 541 and immediately surfaced one real violation
(`infrastructure.email.resend_adapter -> application.ports.email_port`, now a
declared exception like its auth and billing siblings).

This is the gate on the gate: a new package directory must be visible to the
linter, or the linter silently stops covering it.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "reasoner"

# Directories that hold generated or runtime output rather than source. They
# carry no .py files, so they are already skipped by the "has code" check --
# listed here only so a stray script dropped into one is an explicit decision.
NOT_SOURCE = {"graphify-out", "generated_tests", "sandbox_image", "scripts"}


def test_every_directory_holding_python_is_a_real_package():
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if not path.is_dir() or path.name == "__pycache__":
            continue
        if NOT_SOURCE & set(path.relative_to(SRC).parts):
            continue
        if not any(path.glob("*.py")):
            continue
        if not (path / "__init__.py").exists():
            rel = path.relative_to(SRC).as_posix()
            offenders.append(f"{rel} ({len(list(path.glob('*.py')))} modules)")

    assert not offenders, (
        "These directories hold Python but have no __init__.py, so grimp does "
        "not build them into the import graph and import-linter never checks "
        "them. Add an empty __init__.py. Found:\n  " + "\n  ".join(offenders)
    )
