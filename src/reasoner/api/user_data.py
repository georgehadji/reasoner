"""The user-data registry: every store that holds a user's data, in erase order.

Built here, once, and used by all three GDPR routes (`GET /api/account/export`,
`POST /api/account/delete`, `DELETE /api/user/data`), so a store cannot be
exported but not erased, or erased by one route and skipped by another (DAT-10,
DAT-11). `tests/architecture/test_user_data_registry.py` pins which stores exist.

Order is the contract:
  1. content stores (events, vectors, uploads, history, neuro, valkey), which
     need the user id or the upload ids and key on nothing in Postgres;
  2. the Postgres rows, dependants first, the ``users`` row (`profile`) last;
  3. `identity`, the sign-in account, after everything keyed on the user id.
`vectors` precedes `uploads` because it lists the uploads to find their indexes.

`profile` and `identity` are the account itself. `DELETE /api/user/data` is
reachable with a `history:delete` API key and must not close the account, so it
erases `data_stores()`; `POST /api/account/delete` needs the account-delete
scope and erases the whole registry.
"""

from __future__ import annotations

from uuid import UUID

from reasoner.application.ports.user_data import UserDataStore
from reasoner.core.settings import settings

ACCOUNT_STORE_NAMES = frozenset({"profile", "identity"})


async def _pg_pool():
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository

    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    return await PostgresQuotaRepository(dsn, pool_size=2)._get_pool()


class _IdentityStore:
    """The sign-in identity. Left in place, its JWT kept working, and a worker
    that had cached the id kept serving it (audit-remediation-2 BIL-18)."""

    name = "identity"

    async def export(self, user_id: str) -> None:
        return None  # the provider's record of the account, not data we hold

    async def erase(self, user_id: str) -> None:
        from reasoner.api.dependencies import forget_provisioned_user
        from reasoner.infrastructure.auth import get_auth_adapter

        forget_provisioned_user(UUID(user_id))
        await get_auth_adapter().delete_identity(user_id)


def user_data_stores() -> list[UserDataStore]:
    from reasoner.api.history import history_repo
    from reasoner.core.ports.memory_port import get_memory_port
    from reasoner.documents.vector_store import DocumentVectorStore
    from reasoner.infrastructure import uploader
    from reasoner.infrastructure.persistence.event_store import get_event_store
    from reasoner.infrastructure.persistence.upload_usage_repo import get_upload_usage_repo
    from reasoner.infrastructure.persistence.user_data_local import (
        EventsStore,
        HistoryStore,
        NeuroStore,
        UploadsStore,
        ValkeyStore,
        VectorsStore,
    )
    from reasoner.infrastructure.persistence.user_data_pg import pg_user_data_stores
    from reasoner.infrastructure.valkey.client import get_valkey_pool

    return [
        EventsStore(get_event_store),
        VectorsStore(uploader, DocumentVectorStore),
        UploadsStore(uploader, get_upload_usage_repo),
        HistoryStore(history_repo),
        NeuroStore(get_memory_port),
        ValkeyStore(get_valkey_pool),
        *pg_user_data_stores(_pg_pool),
        _IdentityStore(),
    ]


def data_stores() -> list[UserDataStore]:
    """Everything the user produced, without the account itself."""
    return [s for s in user_data_stores() if s.name not in ACCOUNT_STORE_NAMES]
