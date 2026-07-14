"""
Architecture Risk: Streaming closure bug in make_wrapper pattern.

api/streaming.py constructs wrappers in a loop, which risks late-binding
closure issues if the `fn` parameter is reused across iterations. This
test validates that the pattern used is closure-safe.
"""

from __future__ import annotations

import asyncio


class _FakeState:
    """Minimal PipelineState stand-in for wrapper testing."""
    def __init__(self):
        self.visited = []


class _FakeServices:
    """Minimal WorkflowServices stand-in."""
    pass


def test_make_wrapper_closure_safety() -> None:
    """Reproduce the make_wrapper pattern from streaming.py and verify
    each wrapper calls its own fn, not the last iteration's fn."""
    visited = []

    async def fn_a(state, services):
        visited.append("a")

    async def fn_b(state, services):
        visited.append("b")

    async def fn_c(state, services):
        visited.append("c")

    # This mirrors the loop in streaming.py:
    #   def make_wrapper(fn):
    #       async def wrapper(state: PipelineState):
    #           await fn(state, _services)
    #       return wrapper
    wrappers = []
    services = _FakeServices()
    for fn in [fn_a, fn_b, fn_c]:
        def make_wrapper(fn):
            async def wrapper(state):
                await fn(state, services)

            return wrapper

        wrappers.append(make_wrapper(fn))

    state = _FakeState()

    # Run all wrappers
    for w in wrappers:
        asyncio.run(w(state))

    assert visited == ["a", "b", "c"], (
        f"Closure bug detected: visited = {visited}, expected ['a', 'b', 'c']. "
        f"Each wrapper should call its own fn, not all call fn_c."
    )


def test_make_wrapper_with_default_arg_pattern() -> None:
    """Alternative pattern using default argument binding (more explicit)."""
    visited = []

    async def fn_a(state, services):
        visited.append("a")

    async def fn_b(state, services):
        visited.append("b")

    async def fn_c(state, services):
        visited.append("c")

    wrappers = []
    services = _FakeServices()
    for fn in [fn_a, fn_b, fn_c]:
        # The even safer pattern: bind fn as default arg
        async def wrapper(state, _fn=fn):
            await _fn(state, services)

        wrappers.append(wrapper)

    state = _FakeState()
    for w in wrappers:
        asyncio.run(w(state))

    assert visited == ["a", "b", "c"]
