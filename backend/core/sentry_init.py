"""Sentry initialization for the EtOH FastAPI backend.

Reads SENTRY_DSN from env. When missing, the SDK is a no-op (safe in dev).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("etoh.sentry")


def init_sentry(
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    traces_sample_rate: Optional[float] = None,
    release: Optional[str] = None,
) -> bool:
    """Initialize sentry-sdk with FastAPI/Starlette integration.

    Returns True if Sentry was configured, False otherwise.
    """
    dsn = dsn or os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Sentry disabled (no SENTRY_DSN).")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError as e:
        logger.warning("Sentry SDK not installed: %s", e)
        return False

    env = environment or os.environ.get("SENTRY_ENVIRONMENT", "development")
    try:
        rate = traces_sample_rate
        if rate is None:
            rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    except ValueError:
        rate = 0.1

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        release=release or os.environ.get("SENTRY_RELEASE"),
        traces_sample_rate=rate,
        send_default_pii=False,  # GDPR — never send PII by default
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Don't capture HTTPException 4xx as errors (404, 401, 429, 402...)
        before_send=_filter_event,
    )
    logger.info("Sentry enabled (env=%s, traces=%.2f).", env, rate)
    return True


def _filter_event(event, hint):
    """Drop expected client errors (4xx HTTPException) to reduce noise."""
    exc_info = hint.get("exc_info") if hint else None
    if exc_info:
        exc_type, exc, _tb = exc_info
        try:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException) and 400 <= exc.status_code < 500:
                return None
        except Exception:
            pass
    return event
