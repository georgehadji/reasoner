"""Stripe and PayPal webhook receivers with signature verification and idempotency."""

from __future__ import annotations

import json
import os
import logging

import stripe
from fastapi import Request

from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
from reasoner.infrastructure.redis.client import get_redis

logger = logging.getLogger(__name__)

# TTL for webhook deduplication (24 hours to cover retry window)
WEBHOOK_DEDUP_TTL_SECONDS = 86400

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
    redis = get_redis()
    completed_key = f"stripe_webhook:{event_id}:completed"
    processing_key = f"stripe_webhook:{event_id}:processing"
    try:
        if await redis.get(completed_key):
            logger.info("Stripe webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        # Atomic claim: only one worker succeeds; others see None and bail.
        claimed = await redis.set(processing_key, "1", nx=True, ex=300)
        if not claimed:
            logger.info("Stripe webhook already in progress: %s", event_id)
            return {"status": "ok"}
    except Exception as exc:
        logger.warning("Redis dedup check failed (proceeding anyway): %s", exc)

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
        # Still return 200 to prevent Stripe retries (Critical Enhancement 4.3)

    # Mark completed ONLY after successful DB commit
    if success:
        try:
            await redis.setex(completed_key, WEBHOOK_DEDUP_TTL_SECONDS, "1")
            await redis.delete(processing_key)
        except Exception as exc:
            logger.warning("Redis completed-key set failed: %s", exc)
    else:
        try:
            await redis.delete(processing_key)
        except Exception as exc:
            logger.warning("Redis processing-key delete failed: %s", exc)

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
    redis = get_redis()
    completed_key = f"paypal_webhook:{event_id}:completed"
    processing_key = f"paypal_webhook:{event_id}:processing"
    try:
        if await redis.get(completed_key):
            logger.info("PayPal webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        # Atomic claim: only one worker succeeds; others see None and bail.
        claimed = await redis.set(processing_key, "1", nx=True, ex=300)
        if not claimed:
            logger.info("PayPal webhook already in progress: %s", event_id)
            return {"status": "ok"}
    except Exception as exc:
        logger.warning("Redis dedup check failed (proceeding anyway): %s", exc)

    # Process the event
    success = False
    try:
        from reasoner.application.services.billing_service import BillingService
        service = BillingService(adapter)
        await service.handle_webhook(event)
        success = True
    except Exception as exc:
        logger.exception("PayPal webhook processing failed for event %s: %s", event_id, exc)

    if success:
        try:
            await redis.setex(completed_key, WEBHOOK_DEDUP_TTL_SECONDS, "1")
            await redis.delete(processing_key)
        except Exception as exc:
            logger.warning("Redis completed-key set failed: %s", exc)
    else:
        try:
            await redis.delete(processing_key)
        except Exception as exc:
            logger.warning("Redis processing-key delete failed: %s", exc)

    return {"status": "ok"}
