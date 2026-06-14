"""Pricing engine — compute multi-channel sell prices from a cost base.

A simple but realistic rule engine for wine & spirits producers:
- base_cost_eur: production / purchase cost per bottle (excl. VAT)
- target_margin_pct: desired gross margin %
- channel multipliers:
    direct  → light margin (caveau, online)
    chr     → restaurant/bar margin (Sud-Est etc.)
    distrib → wholesaler margin (cuts the producer's share)
    export  → adds shipping/duty + currency cushion
- vat_pct (default 20% FR), bottle weight & volume for shipping estimation.

The engine returns a price *suggestion* per channel + the implied margin & retail
price (HT et TTC). Frontend can override individual channels and persist via
PATCH /api/pricing/products/{id}.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PricingChannel:
    """Default multiplier applied on top of (cost + base margin)."""
    id: str
    label: str
    margin_pct: float          # producer-side margin we keep
    distributor_pct: float     # share kept by the channel partner (caviste, distrib)
    retail_markup_pct: float   # consumer markup at end of chain


# Sensible defaults — overridable from frontend.
DEFAULT_CHANNELS: List[PricingChannel] = [
    PricingChannel(id="direct",  label="Vente directe",         margin_pct=60, distributor_pct=0,  retail_markup_pct=0),
    PricingChannel(id="chr",     label="CHR (Restaurant/Bar)",  margin_pct=40, distributor_pct=30, retail_markup_pct=150),
    PricingChannel(id="caviste", label="Caviste / GMS",         margin_pct=35, distributor_pct=35, retail_markup_pct=40),
    PricingChannel(id="distrib", label="Distributeur",          margin_pct=25, distributor_pct=20, retail_markup_pct=60),
    PricingChannel(id="export",  label="Export (UE/USA)",       margin_pct=30, distributor_pct=25, retail_markup_pct=80),
]


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


def compute_prices(
    *,
    base_cost_eur: float,
    vat_pct: float = 20.0,
    channels: Optional[List[Dict[str, Any]]] = None,
    shipping_eur: float = 0.0,
    duty_pct: float = 0.0,
    currency_buffer_pct: float = 3.0,
) -> Dict[str, Any]:
    """Return per-channel pricing breakdown.

    Returns:
      {
        cost: { base, shipping, duty_adj, total_landed },
        channels: [
          {id, label, producer_price_ht, partner_price_ht, retail_price_ttc,
           producer_margin_pct, retail_markup_pct}
        ],
        notes: [...]
      }
    """
    if base_cost_eur < 0:
        raise ValueError("base_cost_eur must be >= 0")
    chans_in = channels or [asdict(c) for c in DEFAULT_CHANNELS]

    notes: List[str] = []
    out_chans: List[Dict[str, Any]] = []
    for c in chans_in:
        ch_id = c["id"]
        is_export = ch_id == "export"
        cost = base_cost_eur
        # Export: add shipping + duty + small FX buffer
        landed_cost = cost
        if is_export:
            landed_cost += shipping_eur
            landed_cost += landed_cost * (duty_pct / 100.0)
            landed_cost += landed_cost * (currency_buffer_pct / 100.0)
        margin_pct = float(c.get("margin_pct", 30))
        dist_pct = float(c.get("distributor_pct", 0))
        retail_markup_pct = float(c.get("retail_markup_pct", 30))

        # Producer wholesale price HT
        producer_price = landed_cost / max(1 - margin_pct / 100.0, 0.05)
        # Partner (caviste/distributeur) price HT — what they sell to next link
        partner_price = producer_price / max(1 - dist_pct / 100.0, 0.05) if dist_pct > 0 else producer_price
        # Retail TTC = partner * (1+retail_markup) * (1+VAT)
        retail_ttc = partner_price * (1 + retail_markup_pct / 100.0) * (1 + vat_pct / 100.0)

        out_chans.append({
            "id": ch_id,
            "label": c.get("label", ch_id),
            "producer_price_ht": _round2(producer_price),
            "partner_price_ht": _round2(partner_price),
            "retail_price_ttc": _round2(retail_ttc),
            "producer_margin_pct": margin_pct,
            "distributor_pct": dist_pct,
            "retail_markup_pct": retail_markup_pct,
            "landed_cost_ht": _round2(landed_cost),
        })

    return {
        "cost": {
            "base": _round2(base_cost_eur),
            "shipping": _round2(shipping_eur),
            "duty_pct": duty_pct,
            "currency_buffer_pct": currency_buffer_pct,
        },
        "vat_pct": vat_pct,
        "channels": out_chans,
        "notes": notes,
    }


def default_channels_payload() -> List[Dict[str, Any]]:
    return [asdict(c) for c in DEFAULT_CHANNELS]
