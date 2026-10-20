"""A run's ledger reference is server-made, so a reused client id still pays (BIL-1).

The caller's ``client_run_id`` was the ledger reference. The Redis duplicate
guard expires after an hour, and the ledger treats a repeated reference as a
replay that moves no credits. Resending an old id therefore ran for free.
See docs/plans/audit-remediation-2026-10-20.md, BIL-1.
"""

from __future__ import annotations

import pytest

from reasoner.domain.credits import CreditReason, run_reference
from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

_USER = "12345678-1234-5678-1234-567812345678"


def test_references_are_unique_and_keep_the_client_id():
    a, b = run_reference("job-42"), run_reference("job-42")
    assert a != b
    assert a.startswith("job-42:") and b.startswith("job-42:")


def test_missing_client_id_uses_the_kind():
    assert run_reference(None).startswith("run:")
    assert run_reference("", "followup").startswith("followup:")


@pytest.mark.asyncio
async def test_reused_client_run_id_is_charged_each_time():
    repo = InMemoryCreditRepository()
    await repo.record(_USER, 100, CreditReason.ADMIN_ADJUSTMENT, reference_id="seed")

    for _ in range(2):  # same client id, e.g. resent after the 1h guard expired
        await repo.record(_USER, -10, CreditReason.PIPELINE_RUN, reference_id=run_reference("job-42"))

    assert (await repo.get_balance(_USER)).balance == 80


@pytest.mark.asyncio
async def test_the_old_scheme_ran_free():
    """Documents the bug this replaces: the same reference charges once."""
    repo = InMemoryCreditRepository()
    await repo.record(_USER, 100, CreditReason.ADMIN_ADJUSTMENT, reference_id="seed")
    for _ in range(2):
        await repo.record(_USER, -10, CreditReason.PIPELINE_RUN, reference_id="job-42")
    assert (await repo.get_balance(_USER)).balance == 90
