"""Centralised MongoDB client + small datetime helper.

Imported by both server.py and the modular `routes/` package. Avoids circular
imports by isolating the Motor client behind this small module.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME") or "etoh_db"

mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]


def _now() -> datetime:
    """UTC `datetime.now()` — the single source of truth for timestamps."""
    return datetime.now(timezone.utc)


__all__ = ["mongo_client", "db", "_now", "MONGO_URL", "DB_NAME"]
