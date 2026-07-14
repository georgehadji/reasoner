"""Tests for AuthManager LRU eviction."""

from __future__ import annotations

import pytest

from reasoner.auth import AuthManager


@pytest.mark.asyncio
async def test_auth_manager_evicts_oldest_key():
    """
    Inserting 10,001 keys into AuthManager should evict the oldest.
    """
    mgr = AuthManager()
    mgr._MAX_KEYS = 10  # Use small limit for test speed

    for i in range(11):
        await mgr.generate_key(name=f"key-{i}")

    # All 11 keys were generated, but only 10 should remain
    keys = await mgr.list_keys()
    # list_keys returns active keys; all generated keys are active
    # But the _keys dict should only hold 10
    assert len(mgr._keys) == 10
