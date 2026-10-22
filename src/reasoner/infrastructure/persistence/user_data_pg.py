"""Postgres user-data stores (DAT-10, DAT-11): profile, subscriptions, quota,
query log and credit ledger.

One generic store over (table, key column, export columns). Each table's export
columns are one module-level tuple, and ``EXPORT_FIELDS`` collects them so a
live-Postgres test can assert that every column exists in the schema
`alembic upgrade head` builds. The old export selected columns that did not
exist and returned 500 for everyone.

Erase order matters, and ``pg_user_data_stores`` returns it: the rows that hang
off the user go first, the ``users`` row last. ``query_log`` is
``ON DELETE SET NULL``, so deleting only the user would leave its rows behind
without an owner; they are the user's data and are deleted explicitly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

PROFILE_FIELDS = (
    "id", "email", "created_at", "last_login_at", "email_verified", "auth_provider", "avatar_url",
)
SUBSCRIPTION_FIELDS = (
    "tier", "status", "current_period_start", "current_period_end", "cancel_at_period_end",
    "stripe_customer_id", "stripe_sub_id", "paypal_sub_id", "created_at",
)
QUOTA_FIELDS = ("tier", "used_queries", "max_queries", "period_start")
QUERY_LOG_FIELDS = ("preset", "method", "tokens_in", "tokens_out", "cost_usd", "created_at")
CREDIT_LEDGER_FIELDS = (
    "delta", "balance_after", "reason", "reference_id", "description", "created_at",
)

# table -> exported columns; tests/integration/test_user_data_pg.py checks them
# against information_schema.columns.
EXPORT_FIELDS: dict[str, tuple[str, ...]] = {
    "users": PROFILE_FIELDS,
    "subscriptions": SUBSCRIPTION_FIELDS,
    "usage_quotas": QUOTA_FIELDS,
    "query_log": QUERY_LOG_FIELDS,
    "credit_ledger": CREDIT_LEDGER_FIELDS,
}

# A long-lived account can hold more rows than one response should carry
# (critical enhancement 6.7: capped to prevent OOM).
EXPORT_ROW_LIMIT = 1000


class PgUserDataStore:
    def __init__(
        self,
        name: str,
        table: str,
        key_column: str,
        get_pool: Callable[[], Awaitable[Any]],
        *,
        one_row: bool = False,
        order_by: str | None = None,
    ) -> None:
        self.name = name
        self._table = table
        self._key = key_column
        self._get_pool = get_pool
        self._one_row = one_row
        self._order_by = order_by

    async def export(self, user_id: str) -> Any:
        pool = await self._get_pool()
        columns = ", ".join(EXPORT_FIELDS[self._table])
        order = f" ORDER BY {self._order_by} DESC" if self._order_by else ""
        rows = await pool.fetch(
            f"SELECT {columns} FROM {self._table} WHERE {self._key} = $1{order} "
            f"LIMIT {EXPORT_ROW_LIMIT}",
            user_id,
        )
        if self._one_row:
            return dict(rows[0]) if rows else {}
        return [dict(r) for r in rows]

    async def erase(self, user_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(f"DELETE FROM {self._table} WHERE {self._key} = $1", user_id)


def pg_user_data_stores(get_pool: Callable[[], Awaitable[Any]]) -> list[PgUserDataStore]:
    """In erase order: dependants first, the ``users`` row last."""
    return [
        PgUserDataStore("query_log", "query_log", "user_id", get_pool, order_by="created_at"),
        PgUserDataStore(
            "credit_ledger", "credit_ledger", "user_id", get_pool, order_by="created_at"
        ),
        PgUserDataStore("quota", "usage_quotas", "user_id", get_pool, one_row=True),
        PgUserDataStore("subscriptions", "subscriptions", "user_id", get_pool),
        PgUserDataStore("profile", "users", "id", get_pool, one_row=True),
    ]
