"""Add PayPal support and rename external_* columns to provider-specific names

Revision ID: 20260501_003029
Revises: df9629e72f17
Create Date: 2026-05-01 00:30:29.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260501_003029"
down_revision: str | None = "df9629e72f17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rename external_subscription_id → stripe_sub_id
    op.execute("""
        ALTER TABLE subscriptions
        RENAME COLUMN external_subscription_id TO stripe_sub_id;
    """)

    # Rename external_customer_id → stripe_customer_id
    op.execute("""
        ALTER TABLE subscriptions
        RENAME COLUMN external_customer_id TO stripe_customer_id;
    """)

    # Add PayPal subscription ID
    op.execute("""
        ALTER TABLE subscriptions
        ADD COLUMN IF NOT EXISTS paypal_sub_id TEXT;
    """)

    # Create index for PayPal lookups
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_subscriptions_paypal_sub_id
        ON subscriptions(paypal_sub_id);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_subscriptions_paypal_sub_id;
    """)

    op.execute("""
        ALTER TABLE subscriptions
        DROP COLUMN IF EXISTS paypal_sub_id;
    """)

    op.execute("""
        ALTER TABLE subscriptions
        RENAME COLUMN stripe_customer_id TO external_customer_id;
    """)

    op.execute("""
        ALTER TABLE subscriptions
        RENAME COLUMN stripe_sub_id TO external_subscription_id;
    """)
