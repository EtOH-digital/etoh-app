"""Pricing engine routes — compute & persist multi-channel sell prices."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db, _now
from core.security import get_current_user
from core.pricing import compute_prices, default_channels_payload

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


class PriceComputeIn(BaseModel):
    base_cost_eur: float = Field(ge=0)
    vat_pct: float = Field(default=20.0, ge=0, le=50)
    channels: Optional[List[Dict[str, Any]]] = None
    shipping_eur: float = Field(default=0.0, ge=0)
    duty_pct: float = Field(default=0.0, ge=0, le=50)
    currency_buffer_pct: float = Field(default=3.0, ge=0, le=20)


@router.get("/defaults")
async def pricing_defaults():
    """Return the default channel matrix (used by the calculator UI)."""
    return {"channels": default_channels_payload()}


@router.post("/compute")
async def pricing_compute(payload: PriceComputeIn, _user=Depends(get_current_user)):
    """Compute producer wholesale / partner / retail TTC prices for each channel."""
    try:
        result = compute_prices(
            base_cost_eur=payload.base_cost_eur,
            vat_pct=payload.vat_pct,
            channels=payload.channels,
            shipping_eur=payload.shipping_eur,
            duty_pct=payload.duty_pct,
            currency_buffer_pct=payload.currency_buffer_pct,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


class SavePricingIn(BaseModel):
    product_id: str
    pricing: Dict[str, Any]
    base_cost_eur: float


@router.put("/products/{product_id}")
async def save_product_pricing(
    product_id: str,
    payload: SavePricingIn,
    user=Depends(get_current_user),
):
    """Persist a computed pricing snapshot onto a Hub product."""
    res = await db.hub_items.update_one(
        {"id": product_id, "user_id": user["user_id"], "type": "product"},
        {"$set": {
            "pricing.snapshot": payload.pricing,
            "pricing.base_cost_eur": payload.base_cost_eur,
            "pricing.updated_at": _now(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "product not found")
    return {"ok": True, "product_id": product_id}
