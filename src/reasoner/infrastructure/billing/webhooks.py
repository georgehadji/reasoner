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
from reasoner.application.services.billing_service import BillingService

logger = logging.getLogger(__name__)

# TTL for webhook deduplication (24 hours to cover retry window)
WEBHOOK_DEDUP_TTL_SECONDS = 86400


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

    # Two-phase deduplication (Critical Enhancement 4.9 + Audit Fix B.4)
    redis = get_redis()
    completed_key = f"stripe_webhook:{event_id}:completed"
    processing_key = f"stripe_webhook:{event_id}:processing"
    try:
        if await redis.get(completed_key):
            logger.info("Stripe webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        # If another worker is processing, let Stripe retry (it will hit completed on success)
        if await redis.get(processing_key):
            logger.info("Stripe webhook already in progress: %s", event_id)
            return {"status": "ok"}
        await redis.setex(processing_key, 300, "1")  # 5-min processing window
    except Exception as exc:
        logger.warning("Redis dedup check failed (proceeding anyway): %s", exc)

    # Process the event
    success = False
    try:
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

    # Deduplication
    redis = get_redis()
    completed_key = f"paypal_webhook:{event_id}:completed"
    processing_key = f"paypal_webhook:{event_id}:processing"
    try:
        if await redis.get(completed_key):
            logger.info("PayPal webhook deduplicated (already completed): %s", event_id)
            return {"status": "ok"}
        if await redis.get(processing_key):
            logger.info("PayPal webhook already in progress: %s", event_id)
            return {"status": "ok"}
        await redis.setex(processing_key, 300, "1")
    except Exception as exc:
        logger.warning("Redis dedup check failed (proceeding anyway): %s", exc)

    # Process the event
    success = False
    try:
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
