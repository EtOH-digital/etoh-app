"""Admin API router — `etoh.io/studio/admin` back-office.

All endpoints here are protected by the X-Admin-Key header, validated against
the `ETOH_ADMIN_API_KEY` env var via `hmac.compare_digest` (constant-time).
"""

from __future__ import annotations

import hmac
import os
import uuid
from datetime import timedelta
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from core.db import db, _now
from core.subscriptions import PLAN_BY_ID

router = APIRouter(prefix="/api/admin", tags=["admin"])

ETOH_ADMIN_API_KEY = os.environ.get("ETOH_ADMIN_API_KEY", "")


async def require_admin_key(request: Request) -> None:
    """FastAPI dependency: validates the X-Admin-Key header.

    401 if missing, 403 if mismatch, 503 if admin not configured.
    """
    if not ETOH_ADMIN_API_KEY:
        raise HTTPException(503, "admin api not configured")
    provided = request.headers.get("x-admin-key") or request.headers.get("X-Admin-Key")
    if not provided:
        raise HTTPException(401, "missing X-Admin-Key header")
    if not hmac.compare_digest(provided, ETOH_ADMIN_API_KEY):
        raise HTTPException(403, "invalid admin key")


@router.get("/health")
async def admin_health(_: None = Depends(require_admin_key)):
    """Sanity-check endpoint for the admin back-office — proves the key works."""
    return {"ok": True, "service": "etoh-api", "ts": _now().isoformat()}


@router.get("/metrics/summary")
async def admin_metrics_summary(_: None = Depends(require_admin_key)):
    """Aggregated metrics for the admin dashboard (`etoh.io/studio/admin`)."""
    users_count = await db.users.count_documents({})
    active_subs = await db.users.count_documents(
        {"subscription.status": {"$in": ["active", "trialing"]}}
    )
    hub_items = await db.hub_items.count_documents({})

    mrr_cursor = db.users.aggregate([
        {"$match": {"subscription.status": {"$in": ["active", "trialing"]}}},
        {"$group": {"_id": "$subscription.plan_id", "count": {"$sum": 1}}},
    ])
    mrr_eur = 0.0
    by_plan: Dict[str, int] = {}
    async for row in mrr_cursor:
        pid = row["_id"]
        plan = PLAN_BY_ID.get(pid)
        if plan:
            mrr_eur += plan["price_eur"] * row["count"]
            by_plan[pid] = row["count"]

    since = _now() - timedelta(days=30)
    signups_30d = await db.users.count_documents({"created_at": {"$gte": since}})
    llm_events_30d = 0
    try:
        llm_events_30d = await db.llm_events.count_documents({"created_at": {"$gte": since}})
    except Exception:
        pass
    hub_views = 0
    try:
        agg = db.hub_items.aggregate([{"$group": {"_id": None, "total": {"$sum": "$views"}}}])
        async for row in agg:
            hub_views = int(row.get("total") or 0)
    except Exception:
        pass

    return {
        "users_count": users_count,
        "active_subscriptions": active_subs,
        "subscriptions_by_plan": by_plan,
        "mrr_eur": round(mrr_eur, 2),
        "arr_eur": round(mrr_eur * 12, 2),
        "signups_30d": signups_30d,
        "hub_items": hub_items,
        "hub_public_views": hub_views,
        "llm_events_30d": llm_events_30d,
        "generated_at": _now().isoformat(),
    }


@router.post("/users/{user_id}/credits")
async def admin_grant_credits(
    user_id: str,
    payload: Dict[str, Any],
    _: None = Depends(require_admin_key),
):
    """Grant or revoke credits to a user manually (from the admin back-office)."""
    delta = int(payload.get("delta") or 0)
    reason = str(payload.get("reason") or "admin_grant")
    if delta == 0:
        raise HTTPException(400, "delta must be non-zero")
    res = await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": delta}})
    if res.matched_count == 0:
        raise HTTPException(404, "user not found")
    await db.wallet_events.insert_one({
        "id": f"adm_{uuid.uuid4().hex[:10]}",
        "user_id": user_id,
        "credits": delta,
        "source": "admin",
        "reason": reason,
        "created_at": _now(),
    })
    user_doc = await db.users.find_one({"user_id": user_id})
    return {"ok": True, "user_id": user_id, "credits": int(user_doc.get("credits") or 0)}
