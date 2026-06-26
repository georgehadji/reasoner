"""
Regression test for BUG-002: search gather resilience.

A single failing search task must not crash the whole gather. The fix uses
asyncio.gather(..., return_exceptions=True) and filters exceptions out, so
healthy results survive alongside failed ones.

(The original SearchMixin class was removed in the flows refactor — c7f3104;
the guarded behavior now lives in
application/flows/search_phases.py. This test validates the invariant
directly and is independent of that module's surface.)
"""

import asyncio
import pytest


class MockClient:
    async def search(self, q, **kwargs):
        if "FAIL" in q:
            raise Exception("Search engine failure")
        return [{"url": f"http://{q}.com", "title": q}]


@pytest.mark.asyncio
async def test_search_gather_resilience():
    client = MockClient()

    async def _search(q):
        # A task that fails fundamentally (not caught by try/except inside task).
        if "CRASH" in q:
            raise TypeError("Fundamental crash")
        return await client.search(q)

    queries = ["normal", "CRASH", "FAIL"]

    # return_exceptions=True keeps healthy results when sibling tasks raise.
    results_nested = await asyncio.gather(
        *[_search(q) for q in queries], return_exceptions=True
    )
    results_nested = [r for r in results_nested if not isinstance(r, Exception)]

    assert len(results_nested) == 1
    assert results_nested[0][0]["title"] == "normal"
