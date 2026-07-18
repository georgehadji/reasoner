"""Valkey adapter package.

This directory houses Valkey adapters that implement the ports defined
in core/ports/:
  - ValkeyCacheAdapter      → SharedCachePort
  - ValkeyStateAdapter      → DistributedStatePort
  - InMemoryCacheAdapter    → SharedCachePort (fallback)
  - InMemoryStateAdapter    → DistributedStatePort (fallback)
"""

from reasoner.infrastructure.valkey.client import (
    get_valkey_pool,
    set_valkey_pool,
    close_valkey_pool,
)

from reasoner.infrastructure.valkey.cache_adapter import ValkeyCacheAdapter
from reasoner.infrastructure.valkey.state_adapter import ValkeyStateAdapter
from reasoner.infrastructure.valkey.memory_cache_adapter import InMemoryCacheAdapter
from reasoner.infrastructure.valkey.memory_state_adapter import InMemoryStateAdapter

# Deprecated aliases — import explicitly to get the warning:
#   from reasoner.infrastructure.valkey.client import get_redis
