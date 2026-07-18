"""Stripe and PayPal webhook receivers with signature verification and idempotency."""

from __future__ import annotations

import json
import os
import asyncio
import logging

import stripe
from fastapi import Request

from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
from reasoner.infrastructure.valkey.client import get_valkey_pool

logger = logging.getLogger(__name__)

# TTL for webhook deduplication (24 hours to cover retry window)
WEBHOOK_DEDUP_TTL_SECONDS = 86400

# Lazy-initialized dead-letter repo
_dead_letter_repo = None


async def _get_dead_letter_repo():
    """Lazy-initialize the billing dead-letter repository."""
    global _dead_letter_repo
    if _dead_letter_repo is not None:
        return _dead_letter_repo
    try:
        pool = await _get_webhook_pool()
        if pool is not None:
            from reasoner.infrastructure.persistence.billing_deadletter_repo import (
                PostgresBillingDeadLetterRepo,
            )
            _dead_letter_repo = PostgresBillingDeadLetterRepo(pool)
            await _dead_letter_repo._ensure_table()
    except Exception as exc:
        logger.warning("Dead-letter repo init failed: %s", exc)
    return _dead_letter_repo


async def _record_webhook_failure(
    provider: str,
    event_type: str,
    payload: dict,
    error: str,
) -> None:
    """Record a webhook failure: metric + dead-letter + domain event.

    This is called from the except block of both webhook handlers.
    It is deliberately fire-and-forget: failures here must never propagate
    (the webhook handler always returns HTTP 200).
    """
    # 1. Prometheus counter
    try:
        from reasoner.metrics import WEBHOOK_PROCESSING_FAILURES
        WEBHOOK_PROCESSING_FAILURES.labels(provider=provider, event_type=event_type).inc()
    except Exception as exc:
        logger.warning("Failed to increment webhook failure metric: %s", exc)

    # 2. Durable dead-letter storage
    try:
        repo = await _get_dead_letter_repo()
        if repo is not None:
            await repo.record_failure(provider, event_type, payload, error)
    except Exception as exc:
        logger.warning("Failed to record webhook failure to dead-letter: %s", exc)

    # 3. Domain event on the bus
    try:
        from reasoner.application.event_bus.bus import get_event_bus
        from reasoner.core.events.domain_events import (
            SaaSEventType,
            make_event,
        )
        bus = get_event_bus()
        event = make_event(
            SaaSEventType.WEBHOOK_PROCESSING_FAILED,
            aggregate_id=f"{provider}:{event_type}",
            version=1,
            metadata={
                "provider": provider,
                "event_type": event_type,
                "error": error,
            },
        )
        # Fire-and-forget: don't block the webhook response on the bus
        asyncio.ensure_future(bus.publish(event))
    except Exception as exc:
        logger.warning("Failed to emit webhook failure event: %s", exc)

# ─── DB-backed idempotency (primary guard; survives Redis failure) ────────────

_webhook_pool = None


async def _get_webhook_pool():
    """Lazy-initialize a small asyncpg pool for webhook idempotency writes."""
    global _webhook_pool
    if _webhook_pool is not None:
        return _webhook_pool
    try:
        import asyncpg
        from reasoner.core.settings import settings
        if not settings.DATABASE_URL:
            return None
        dsn = settings.DATABASE_URL.replace("+asyncpg", "")
        _webhook_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
        async with _webhook_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_webhooks (
                    event_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (event_id, provider)
                )
            """)
    except Exception as exc:
        logger.warning("Webhook DB pool init failed (will rely on Redis dedup): %s", exc)
        _webhook_pool = None
    return _webhook_pool


async def _db_claim_webhook(event_id: str, provider: str) -> bool:
    """Attempt to claim a webhook event via DB INSERT. Returns True if claimed (first time)."""
    pool = await _get_webhook_pool()
    if pool is None:
        return True  # DB unavailable — fall through to Redis guard
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "INSERT INTO processed_webhooks (event_id, provider) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                event_id, provider,
            )
            # asyncpg returns "INSERT 0 N" — N=1 means inserted (first time), N=0 means duplicate
            return result.endswith("1")
    except Exception as exc:
        logger.warning("Webhook DB claim failed for %s/%s (falling through to Redis): %s",
                       provider, event_id, exc)
        return True  # DB failed — fall through to Redis guard


async def handle_stripe_webhook(request: Request) -> dict:
    """
    Receive and process Stripe webhook events.

    Returns:
        {"status": "ok"} with HTTP 200 even on processing errors
        to prevent infinite Stripe retries (Critical Enhancement 4.3).
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    # Verify signature if secret is configured
    if webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except ValueError:
            logger.warning("Stripe webhook: invalid payload")
            return {"status": "ok"}
        except stripe.error.SignatureVerificationError:
            from reasoner.metrics import STRIPE_WEBHOOK_SIG_FAILURES
            STRIPE_WEBHOOK_SIG_FAILURES.inc()
            logger.warning("Stripe webhook: invalid signature")
            return {"status": "ok"}
    else:
        logger.error("Stripe webhook: STRIPE_WEBHOOK_SECRET not configured. Event ignored.")
        # Return 200 to prevent Stripe retries, but do NOT process the event
        return {"status": "misconfigured"}

    event_id = event.get("id", "unknown")
    event_type = event.get("type", "unknown")
    logger.info("Stripe webhook received: %s (id=%s)", event_type, event_id)

    # DB-backed idempotency (primary guard — survives Redis failure)
    if not await _db_claim_webhook(event_id, "stripe"):
        logger.info("Stripe webhook deduplicated (DB guard): %s", event_id)
        return {"status": "ok"}

    # Two-phase deduplication (Critical Enhancement 4.9 + Audit Fix B.4)
    # Uses atomic SET NX to eliminate the TOCTOU race between GET and SETEX.
    valkey = get_valkey_pool()
    completed_key = f"stripe_webhook:{event_id}:completed"
    processing_key = f"stripe_webhook:{event_id}:processing"
    try:
        if await valkey.get(completed_key):
            logger.info("Stripe webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        # Atomic claim: only one worker succeeds; others see None and bail.
        claimed = await valkey.set(processing_key, "1", nx=True, ex=300)
        if not claimed:
            logger.info("Stripe webhook already in progress: %s", event_id)
            return {"status": "ok"}
    except Exception as exc:
        logger.warning("Valkey dedup check failed (proceeding anyway): %s", exc)

    # Process the event
    success = False
    try:
        from reasoner.application.services.billing_service import BillingService
        adapter = StripeBillingAdapter()
        service = BillingService(adapter)
        await service.handle_webhook(event)
        success = True
    except Exception as exc:
        logger.exception("Stripe webhook processing failed for event %s: %s", event_id, exc)
        # Record the failure durably (metric + dead-letter + event)
        await _record_webhook_failure("stripe", event_type, dict(event), str(exc))
        # Still return 200 to prevent Stripe retries (Critical Enhancement 4.3)

    # Mark completed ONLY after successful DB commit
    if success:
        try:
            await valkey.setex(completed_key, WEBHOOK_DEDUP_TTL_SECONDS, "1")
            await valkey.delete(processing_key)
        except Exception as exc:
            logger.warning("Valkey completed-key set failed: %s", exc)
    else:
        try:
            await valkey.delete(processing_key)
        except Exception as exc:
            logger.warning("Valkey processing-key delete failed: %s", exc)

    return {"status": "ok"}


async def handle_paypal_webhook(request: Request) -> dict:
    """Receive and process PayPal webhook events.

    Returns {"status": "ok"} with HTTP 200 to prevent PayPal retries.
    """
    body_bytes = await request.body()
    try:
        event = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        logger.warning("PayPal webhook: invalid JSON payload")
        return {"status": "ok"}

    event_id = event.get("id", "unknown")
    event_type = event.get("event_type", "unknown")
    logger.info("PayPal webhook received: %s (id=%s)", event_type, event_id)

    # Basic verification
    adapter = PayPalBillingAdapter()
    headers = dict(request.headers)
    try:
        verified = await adapter.verify_webhook_signature(headers, body_bytes.decode("utf-8"))
        if not verified:
            logger.warning("PayPal webhook: signature verification failed")
            return {"status": "ok"}
    except Exception as exc:
        logger.warning("PayPal webhook verification error: %s", exc)

    # DB-backed idempotency (primary guard — survives Redis failure)
    if not await _db_claim_webhook(event_id, "paypal"):
        logger.info("PayPal webhook deduplicated (DB guard): %s", event_id)
        return {"status": "ok"}

    # Deduplication
    valkey = get_valkey_pool()
    completed_key = f"paypal_webhook:{event_id}:completed"
    processing_key = f"paypal_webhook:{event_id}:processing"
    try:
        if await valkey.get(completed_key):
            logger.info("PayPal webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        # Atomic claim: only one worker succeeds; others see None and bail.
        claimed = await valkey.set(processing_key, "1", nx=True, ex=300)
        if not claimed:
            logger.info("PayPal webhook already in progress: %s", event_id)
            return {"status": "ok"}
    except Exception as exc:
        logger.warning("Valkey dedup check failed (proceeding anyway): %s", exc)

    # Process the event
    success = False
    try:
        from reasoner.application.services.billing_service import BillingService
        service = BillingService(adapter)
        await service.handle_webhook(event)
        success = True
    except Exception as exc:
        logger.exception("PayPal webhook processing failed for event %s: %s", event_id, exc)
        # Record the failure durably (metric + dead-letter + event)
        await _record_webhook_failure("paypal", event_type, dict(event), str(exc))

    if success:
        try:
            await valkey.setex(completed_key, WEBHOOK_DEDUP_TTL_SECONDS, "1")
            await valkey.delete(processing_key)
        except Exception as exc:
            logger.warning("Valkey completed-key set failed: %s", exc)
    else:
        try:
            await valkey.delete(processing_key)
        except Exception as exc:
            logger.warning("Valkey processing-key delete failed: %s", exc)

    return {"status": "ok"}
