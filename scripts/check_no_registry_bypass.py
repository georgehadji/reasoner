"""CI guard: application/domain/core must not directly import infrastructure.llm.registry.

Complements .importlinter's layers contract, which only forbids reverse
(infrastructure -> application) imports and cannot cleanly express "no DIRECT
import of this one module" without flooding false positives across the whole
transitive graph — registry is legitimately reachable via infrastructure.llm.router,
which application already depends on. This checks direct import statements only,
via AST, so it doesn't trip on that transitive path.

Usage: python scripts/check_no_registry_bypass.py
Exit 0 = clean, 1 = violations found (wire into CI as a required step).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN = "reasoner.infrastructure.llm.registry"
SCAN_ROOTS = ("src/reasoner/application", "src/reasoner/domain", "src/reasoner/core")


def direct_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == FORBIDDEN:
            hits.append(node.lineno)
        elif isinstance(node, ast.Import):
            hits.extend(node.lineno for alias in node.names if alias.name == FORBIDDEN)
    return hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations = []
    for scan_root in SCAN_ROOTS:
        for path in (root / scan_root).rglob("*.py"):
            violations.extend(f"{path.relative_to(root)}:{lineno}" for lineno in direct_imports(path))

    if violations:
        print(f"Direct import of {FORBIDDEN} found outside infrastructure/api:")
        for v in violations:
            print(f"  {v}")
        print("\nUse core.ports.model_registry_port.get_model_registry_port() instead.")
        return 1

    print(f"OK: no direct application/domain/core imports of {FORBIDDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
