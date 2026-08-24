# Context: Persistence

## Directory: `src/reasoner/infrastructure/persistence`

## Description
Relational database adapters, SQLAlchemy models, and session management configurations.

## Files
- **`__init__.py`**: Infrastructure Persistence Package
- **`api_key_repo_memory.py`**: In-memory ApiKeyRepository — for tests and single-process local development.
- **`api_key_repo_postgres.py`**: user_id in the predicate prevents cross-account revocation by id guessing.
- **`auth_store.py`**: Schema version for future migrations
- **`billing_deadletter_repo.py`**: Index for listing failures by provider and replay status
- **`cached_quota_repo.py`**: Cache-aside decorator for QuotaRepository.
- **`cached_subscription_repo.py`**: Cached when a user has no subscription row at all — the common free-tier
- **`credit_repo_memory.py`**: In-memory CreditRepository — for tests and single-process local development.
- **`credit_repo_postgres.py`**: ── Reads ──────────────────────────────────────────────────────────
- **`error_store.py`**: Error Persistence Layer
- **`event_store.py`**: Delegate connection lifecycle to dedicated module
- **`event_store_connection.py`**: Code or resource asset facilitating system functionality.
- **`feedback_store.py`**: Code or resource asset facilitating system functionality.
- **`pipeline_ownership_repo.py`**: Default location of the retired JSON ownership store (formerly
- **`postgres_store.py`**: Retained references to background publish tasks to prevent premature GC.
- **`quota_repo_postgres.py`**: User has no quota row yet — create with free defaults
- **`snapshots.py`**: Snapshot Strategy for Aggregate Performance
- **`subscription_repo.py`**: Lazy initialize the class-level lock
- **`telemetry_store.py`**: Code or resource asset facilitating system functionality.

## Subfolders
*No subfolders in this directory.*
