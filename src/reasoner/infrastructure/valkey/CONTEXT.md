# Context: Valkey

## Directory: `src/reasoner/infrastructure/valkey`

## Description
Valkey in-memory key-value database adapters and cache managers.

## Files
- **`__init__.py`**: Valkey adapter package.
- **`cache_adapter.py`**: ValkeyCacheAdapter — implements SharedCachePort backed by Valkey.
- **`client.py`**: Shared Valkey connection pool — canonical replacement for redis/client.py.
- **`memory_cache_adapter.py`**: InMemoryCacheAdapter — implements SharedCachePort backed by a local dict.
- **`memory_state_adapter.py`**: InMemoryStateAdapter — implements DistributedStatePort backed by a local dict.
- **`state_adapter.py`**: ValkeyStateAdapter — implements DistributedStatePort backed by Valkey.

## Subfolders
- **`scripts`**: Optimized Lua scripts executed inside Valkey database instances.
