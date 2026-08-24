# Context: Billing

## Directory: `src/reasoner/infrastructure/billing`

## Description
Payment gateway adapters (PayPal, Stripe) and billing credit ledger managers.

## Files
- **`__init__.py`**: Billing infrastructure — Stripe and PayPal adapters and webhook handlers.
- **`paypal_adapter.py`**: Create a subscription
- **`stripe_adapter.py`**: Lookup Stripe customer by user_id (stored in metadata)
- **`webhooks.py`**: TTL for webhook deduplication (24 hours to cover retry window)

## Subfolders
*No subfolders in this directory.*
