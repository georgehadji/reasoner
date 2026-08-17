"""Capability coverage gate — security-remediation-plan.md Phase 2 item 4.

Not a hand-maintained list: this scans the actual FastAPI route source for
calls into the credit-reservation path (``reserve_or_402``,
``_reserve_image_credits``) and cross-checks the route each call sits under
against ``core.capabilities.CAPABILITY_POLICY``. A new provider-costing route
that reserves credits without also registering a ``Capability`` fails this
test -- that's the actual "impossible to add a costed route without
selecting a policy" enforcement the plan asks for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from reasoner.core.capabilities import CAPABILITY_POLICY

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).parent.parent
SCANNED_FILES = [
    REPO_ROOT / "src/reasoner/api/__init__.py",
    REPO_ROOT / "src/reasoner/api/routes/agent.py",
    REPO_ROOT / "src/reasoner/api/routes/images.py",
]

_ROUTE_DECORATOR = re.compile(r'@(?:app|router)\.(?:get|post|put|delete)\("([^"]+)"')
_ROUTER_PREFIX = re.compile(r'APIRouter\([^)]*prefix="([^"]+)"')
_RESERVATION_CALL = re.compile(r"\breserve_or_402\(|\b_reserve_image_credits\(")

ALL_REGISTERED_ROUTES = frozenset(
    route for policy in CAPABILITY_POLICY.values() for route in policy.routes
)


def _scan_routes(files: list[Path]) -> tuple[set[str], set[str]]:
    """Scan for route decorators and reservation calls across *files*.

    Heuristic, not a full parser: tracks the most recently seen route
    decorator and attributes any reservation call found before the next
    decorator to that route. Matches this codebase's consistent one-route-
    per-decorated-function style.

    Static source scanning rather than introspecting a live FastAPI app:
    this app wraps ``include_router`` with something that leaves
    ``app.routes`` full of opaque ``_IncludedRouter`` placeholders instead of
    flattened ``APIRoute`` objects (confirmed -- ``route.path`` is ``None``
    for every included sub-router), so runtime route-table walking isn't a
    reliable source of truth here.

    Returns (all_declared_routes, routes_that_reserve_credits).
    """
    all_routes: set[str] = set()
    reserving_routes: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        prefix_match = _ROUTER_PREFIX.search(text)
        prefix = prefix_match.group(1) if prefix_match else ""

        current_route: str | None = None
        for line in text.splitlines():
            decorator_match = _ROUTE_DECORATOR.search(line)
            if decorator_match:
                current_route = prefix + decorator_match.group(1)
                all_routes.add(current_route)
                continue
            if _RESERVATION_CALL.search(line) and current_route:
                reserving_routes.add(current_route)
    return all_routes, reserving_routes


def test_every_reservation_call_site_has_a_registered_capability() -> None:
    _all_routes, routes_that_reserve = _scan_routes(SCANNED_FILES)

    assert routes_that_reserve, (
        "Scan found zero routes calling reserve_or_402/_reserve_image_credits -- "
        "the scan itself is broken, not that reservation was removed."
    )

    uncovered = routes_that_reserve - ALL_REGISTERED_ROUTES
    assert not uncovered, (
        f"Route(s) {uncovered} reserve credits but aren't listed under any "
        "Capability in core/capabilities.py -- add a CapabilityPolicy entry "
        "covering them."
    )


def test_every_registered_route_actually_exists_in_the_scanned_source() -> None:
    """Catches the opposite drift: a stale/typo'd route path in
    CAPABILITY_POLICY that no longer matches a real route decorator."""
    all_routes, _reserving = _scan_routes(SCANNED_FILES)

    for policy in CAPABILITY_POLICY.values():
        for route in policy.routes:
            assert route in all_routes, (
                f"CAPABILITY_POLICY references {route!r}, which isn't a route "
                f"decorator found in {[str(f) for f in SCANNED_FILES]} -- stale entry?"
            )
