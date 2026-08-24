# Context: Ports

## Directory: `src/reasoner/core/ports`

## Description
Core-level abstract interfaces defining adapters for low-level platform features.

## Files
- **`__init__.py`**: Port interfaces for hexagonal architecture.
- **`api_key_repository.py`**: Port: persistence contract for user-owned API keys.
- **`capability_registry_port.py`**: Port: capability registry for model profiles (ACR Phase 2).
- **`circuit_breaker_port.py`**: Port interface for circuit breaker — infrastructure provides concrete implementation.
- **`code_executor.py`**: Core port for code execution — Hexagonal DDD port layer.
- **`credit_repository.py`**: Port: persistence contract for the credit ledger.
- **`crypto_port.py`**: Port interface for at-rest encryption — infrastructure/security provides the adapter.
- **`distributed_state_port.py`**: Distributed state port — atomic operations and Lua scripting.
- **`file_search_port.py`**: Port for semantic search over uploaded file chunks.
- **`llm_port.py`**: Port interface for LLM access — ProviderRouter implements this.
- **`memory_port.py`**: Port interface for long-term memory — the neuro package provides the adapter.
- **`model_registry_port.py`**: Port interface for model registry — infrastructure provides concrete implementation.
- **`routing_constraint_port.py`**: ACR routing constraint port (Phase 4).
- **`search_port.py`**: Search service port interface — implemented by search adapters in infrastructure/.
- **`shared_cache_port.py`**: Shared cache port — key-value cache with TTL support.
- **`telemetry_port.py`**: Port: telemetry persistence for cross-run analytics.
- **`translation_port.py`**: Port for translation — CompositeTranslator implements this.
- **`watermark_port.py`**: Code or resource asset facilitating system functionality.

## Subfolders
*No subfolders in this directory.*
