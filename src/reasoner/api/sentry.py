"""Sentry initialization for FastAPI.

Critical Enhancement 7.5: traces_sample_rate starts at 1.0 for early-stage
products and can be reduced as traffic grows.
"""

from __future__ import annotations

import logging

from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration
    _HAS_SENTRY = True
except ImportError:
    _HAS_SENTRY = False


def init_sentry() -> None:
    if not _HAS_SENTRY:
        logger.debug("sentry-sdk not installed, skipping Sentry initialization")
        return

    if not settings.SENTRY_DSN:
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=0.1,
    )
