"""Concurrency tests for AuthManager."""

import asyncio

import pytest

from reasoner.auth import AuthManager


class TestAuthManagerConcurrency:
    """Verify auth state remains consistent under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_generate_key_all_unique(self):
        manager = AuthManager()
        count = 50

        keys = await asyncio.gather(*[
            manager.generate_key(f"key-{i}")
            for i in range(count)
        ])

        assert len(keys) == count
        assert len(set(keys)) == count, "All generated keys must be unique"
        assert len(manager._keys) == count

    @pytest.mark.asyncio
    async def test_concurrent_generate_and_authenticate(self):
        from reasoner.auth import AuthenticationError
        manager = AuthManager()

        async def generate_batch():
            for i in range(25):
                await manager.generate_key(f"gen-{i}")

        async def authenticate_batch():
            results = []
            for i in range(25):
                # Most of these will fail (key doesn't exist yet), but the
                # operation itself must not corrupt internal state.
                try:
                    result = await manager.authenticate(f"invalid-key-{i}")
                    results.append(result)
                except AuthenticationError:
                    results.append(None)
            return results

        await asyncio.gather(generate_batch(), authenticate_batch())

        # Internal dict should still contain exactly the 25 generated keys
        assert len(manager._keys) == 25

    @pytest.mark.asyncio
    async def test_revoke_key_under_concurrent_access(self):
        manager = AuthManager()
        raw_keys = await asyncio.gather(*[
            manager.generate_key(f"revoke-{i}")
            for i in range(10)
        ])

        # Revoke half concurrently
        await asyncio.gather(*[
            manager.revoke_key(manager._hash_key(raw_keys[i]))
            for i in range(0, 10, 2)
        ])

        # All 10 keys still exist in _keys, but 5 are inactive
        active_count = sum(1 for k in manager._keys.values() if k.is_active)
        assert active_count == 5
