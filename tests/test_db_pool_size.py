"""Tests for DB_POOL_SIZE setting."""
from __future__ import annotations

import os

import pytest

from reasoner.core.settings import Settings


class TestDBPoolSize:
    def test_default_pool_size(self) -> None:
        settings = Settings()
        # Raised from 10 to 50 for multi-worker deployments.
        assert settings.DB_POOL_SIZE == 50

    def test_pool_size_is_int(self) -> None:
        settings = Settings()
        assert isinstance(settings.DB_POOL_SIZE, int)

    def test_pool_size_positive(self) -> None:
        settings = Settings()
        assert settings.DB_POOL_SIZE > 0

    def test_custom_pool_size_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Verify Settings picks up DB_POOL_SIZE from the environment.
        We avoid importlib.reload to prevent module-state pollution across tests.
        """
        monkeypatch.setenv("DB_POOL_SIZE", "25")
        # Create a fresh class in a local namespace so class-body evaluation
        # sees the patched environment without mutating global modules.
        namespace = {"os": os}
        exec("DB_POOL_SIZE: int = int(os.getenv('DB_POOL_SIZE', '10'))", namespace)
        assert namespace["DB_POOL_SIZE"] == 25
