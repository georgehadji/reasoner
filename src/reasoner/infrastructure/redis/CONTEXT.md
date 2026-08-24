# Context: Redis

## Directory: `src/reasoner/infrastructure/redis`

## Description
Redis cache adapters, session stores, and rate-limiting helper implementations.

## Files
- **`client.py`**: Shared Redis connection pool for all Redis-backed features.
- **`in_memory.py`**: Code or resource asset facilitating system functionality.
- **`run_state.py`**: Redis key names

## Subfolders
- **`scripts`**: Optimized Lua scripts executed atomically inside Redis for concurrency and token buckets.
