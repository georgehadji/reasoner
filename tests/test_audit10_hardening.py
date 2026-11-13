"""Audit-10 hardening: upload/image admission, ledger fail-closed, orphan
reservations, TRUSTED_PROXIES guard, refund/dispute clawback."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from reasoner.api import dependencies as deps
from reasoner.api.routes import images, uploads
from reasoner.api.run_admission import FlatCharge
from reasoner.api.schemas import GenerateImageRequest
from reasoner.application.services import billing_service as bs
from reasoner.application.services.credit_service import CreditService
from reasoner.application.services.estimate_service import (
    estimate_image_cost,
    estimate_upload_cost,
)
from reasoner.domain.credits import CreditReason
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier, User
from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

pytestmark = pytest.mark.unit


def _user() -> User:
    return User(id=uuid4(), email="t@example.com", created_at=datetime.now(UTC))


# A. upload admission -------------------------------------------------------


class _Form:
    def __init__(self, files):
        self._files = files

    def getlist(self, _k):
        return self._files


class _File:
    def __init__(self, name):
        self.filename = name
        self._data = [b"abc", b""]

    async def read(self, _n):
        return self._data.pop(0)


class _Req:
    headers: dict = {}

    def __init__(self, files):
        self._files = files

    async def form(self):
        return _Form(self._files)


@pytest.fixture
def upload_env(monkeypatch):
    calls = {"admit": [], "close": []}

    async def admit(request, *, user, cost_usd, kind):
        calls["admit"].append((cost_usd, kind))
        return FlatCharge(str(user.id), f"{kind}:x", 5, cost_usd)

    async def close(charge, *, served):
        calls["close"].append(served)

    async def save(content, filename, user_id=None, force_ocr=False):
        if filename == "boom.png":
            raise RuntimeError("vision down")
        return {"success": True, "stored_bytes": 0}

    usage = SimpleNamespace(
        reserve=AsyncMock(return_value=True), adjust=AsyncMock(), get=AsyncMock(return_value=0)
    )
    monkeypatch.setattr(uploads, "admit_flat_charge", admit)
    monkeypatch.setattr(uploads, "close_flat_charge", close)
    monkeypatch.setattr(uploads, "save_uploaded_file", save)
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: usage)
    return calls


async def _upload(files, force_ocr=False):
    return await uploads.upload_file(
        _Req(files), force_ocr=force_ocr, user=_user(), rate_limit_checked=True, csrf_checked=True
    )


async def test_image_upload_is_admitted_and_kept_on_success(upload_env):
    await _upload([_File("a.png"), _File("b.txt")])
    assert upload_env["admit"] == [(estimate_upload_cost(1), "upload")]
    assert upload_env["close"] == [True]


async def test_failed_image_upload_gives_the_hold_back(upload_env):
    with pytest.raises(HTTPException):
        await _upload([_File("boom.png")])
    assert upload_env["close"] == [False]


async def test_text_upload_and_force_ocr_are_not_charged(upload_env):
    await _upload([_File("a.txt")])
    await _upload([_File("a.png")], force_ocr=True)
    assert upload_env["admit"] == []


# B. image hold priced premium unless budget was explicit --------------------


async def test_unset_preset_is_priced_premium(monkeypatch):
    seen = []

    async def admit(request, *, user, cost_usd, kind):
        seen.append(cost_usd)
        raise HTTPException(status_code=402)

    monkeypatch.setattr(images, "admit_flat_charge", admit)
    for body in (
        GenerateImageRequest(prompt="x", num_images=1),
        GenerateImageRequest(prompt="x", num_images=1, preset="image-gen-budget"),
    ):
        with pytest.raises(HTTPException):
            await images.generate_image_endpoint(
                request=None, body=body, user=_user(), rate_limit_checked=True,
                csrf_checked=True, quota=None,
            )
    assert seen[0] == await estimate_image_cost("premium", 1)
    assert seen[1] == await estimate_image_cost("budget", 1)
    assert seen[0] > seen[1]


# D. ledger errors fail closed -----------------------------------------------


async def test_require_credits_fails_closed_on_ledger_error(monkeypatch):
    svc = SimpleNamespace(get_balance=AsyncMock(side_effect=TimeoutError()))
    monkeypatch.setattr(deps, "_require_persistence", lambda *_: None)
    monkeypatch.setattr(deps, "_get_credit_service", lambda: svc)
    monkeypatch.setattr(deps, "_top_up_allowance", AsyncMock())
    with pytest.raises(HTTPException) as e:
        await deps.require_credits(user=_user())
    assert e.value.status_code == 503


async def test_reserve_or_402_fails_closed_on_ledger_error(monkeypatch):
    import reasoner.application.services.run_metering as rm

    monkeypatch.setattr(deps, "_persistence_is_configured", lambda: True)
    monkeypatch.setattr(deps, "_require_persistence", lambda *_: None)
    monkeypatch.setattr(rm, "reserve_run_budget", AsyncMock(side_effect=TimeoutError()))
    with pytest.raises(HTTPException) as e:
        await deps.reserve_or_402(user_id=str(uuid4()), preset="p", problem="x", reference_id="r")
    assert e.value.status_code == 503


# F. TRUSTED_PROXIES production guard ----------------------------------------


def _import_settings(**extra):
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "ENVIRONMENT": "production",
        "CSRF_SECRET": "x" * 40,
        "ADMIN_API_KEY": "y" * 40,
        "JWT_SECRET_KEY": "z" * 40,
        "EXEC_SANDBOX_ENABLED": "false",
        "TRUSTED_PROXIES": "",
        "ALLOW_NO_TRUSTED_PROXIES": "",
        **extra,
    }
    return subprocess.run(
        [sys.executable, "-c", "import reasoner.core.settings"],
        env=env, capture_output=True, text=True,
    )


def test_production_refuses_empty_trusted_proxies():
    proc = _import_settings()
    assert proc.returncode != 0 and "TRUSTED_PROXIES" in proc.stderr


@pytest.mark.parametrize(
    "extra", [{"TRUSTED_PROXIES": "10.0.0.1"}, {"ALLOW_NO_TRUSTED_PROXIES": "true"}]
)
def test_production_starts_with_proxies_or_opt_out(extra):
    assert _import_settings(**extra).returncode == 0


# G. orphaned reservations ----------------------------------------------------


async def test_orphan_sweep_releases_only_stale_unsettled_reservations():
    repo = InMemoryCreditRepository()
    svc = CreditService(repo)
    uid = str(uuid4())
    for ref in ("dead", "settled", "released", "fresh"):
        await repo.record(
            uid, -10, CreditReason.PIPELINE_RUN, f"{ref}:reserve", allow_overdraft=True
        )
    await repo.record(uid, -3, CreditReason.PIPELINE_RUN, "settled", allow_overdraft=True)
    await repo.record(uid, 10, CreditReason.REFUND, "released:release", allow_overdraft=True)
    before = (await repo.get_balance(uid)).balance
    old = datetime.now(UTC) - timedelta(hours=2)
    repo._entries[uid] = [
        e if (e.reference_id or "").startswith("fresh") else replace(e, created_at=old)
        for e in repo._entries[uid]
    ]
    cutoff = datetime.now(UTC) - timedelta(hours=1)

    assert await svc.release_orphaned_reservations(cutoff) == 1
    assert (await repo.get_balance(uid)).balance == before + 10
    assert await svc.release_orphaned_reservations(cutoff) == 0  # idempotent


# H. refund / dispute clawback -------------------------------------------------


def _sub():
    return Subscription(
        id=uuid4(), user_id=uuid4(), tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.PAST_DUE, stripe_customer_id="cus_1",
    )


@pytest.fixture
def credits_wired():
    repo = InMemoryCreditRepository()
    svc = CreditService(repo)
    bs.set_credit_service_provider(lambda: svc)
    yield repo
    bs.set_credit_service_provider(None)


@pytest.mark.parametrize(
    "event_type,obj,key,status_set",
    [
        ("charge.dispute.created", {"id": "dp_1", "amount": 500}, "dispute:dp_1", True),
        (
            "charge.refunded",
            {"id": "ch_1", "amount_refunded": 500, "refunded": True},
            "refund:ch_1",
            True,
        ),
        (
            "charge.refunded",
            {"id": "ch_2", "amount_refunded": 100, "refunded": False},
            "refund:ch_2",
            False,
        ),
    ],
)
async def test_chargeback_events_claw_back_idempotently(
    credits_wired, event_type, obj, key, status_set
):
    sub = _sub()
    repo = SimpleNamespace(
        get_subscription_by_user=AsyncMock(
            return_value=SimpleNamespace(stripe_subscription_id="sub_1")
        ),
        set_subscription_status=AsyncMock(),
    )
    svc = bs.BillingService(port=None)
    for _ in range(2):
        await svc._apply_webhook(event_type, sub, repo, None, obj)

    entries = await credits_wired.list_entries(str(sub.user_id))
    assert [(e.reference_id, e.delta < 0) for e in entries] == [(key, True)]
    assert repo.set_subscription_status.await_count == (2 if status_set else 0)
    if status_set:
        assert repo.set_subscription_status.await_args.args[:2] == ("sub_1", "past_due")
