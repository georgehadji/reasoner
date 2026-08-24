"""
Quota Repository Port — Abstract interface for quota persistence.

Implementations may use PostgreSQL, Redis, or a hybrid cache-aside strategy.
"""

from __future__ import annotations

from typing import Protocol

from reasoner.domain.saas import QuotaResult, UsageQuota


class QuotaRepository(Protocol):
    """Port for usage quota storage and enforcement."""

    async def get_quota(self, user_id: str) -> UsageQuota:
        """Fetch the current quota for a user."""
        ...

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        """
        Atomically check remaining quota and increment used_queries by 1.

        This MUST be transactional (SELECT ... FOR UPDATE or equivalent)
        to prevent race conditions under concurrent requests.
        """
        ...

    async def reset_monthly(self, user_id: str) -> None:
        """Reset used_queries to 0 and update period_start to current month."""
        ...

    async def log_query(
        self,
        user_id: str,
        preset: str,
        method: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        """Append an immutable entry to the query audit log."""
        ...
