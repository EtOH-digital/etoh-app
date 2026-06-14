"""Idempotent seed script for EtOH Stripe subscription Products + Prices.

Run from /app/backend:
    python scripts/seed_stripe_subscriptions.py

It creates (or reuses) Stripe Products and recurring monthly Prices for the
Pro / Business / Premium tiers in TEST mode, then prints the resulting
`STRIPE_PRICE_*_MONTHLY` env vars to append to backend/.env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

import stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
if not STRIPE_SECRET_KEY:
    print("ERROR: STRIPE_SECRET_KEY missing in backend/.env", file=sys.stderr)
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY

PRODUCTS = [
    {
        "product_id": "etoh_pro_monthly",
        "name": "EtOH Pro",
        "description": "EtOH Pro — 19€/mois, 300 crédits inclus, Hub public + chat IA + RAG.",
        "lookup_key": "etoh_pro_monthly_eur_v1",
        "unit_amount": 1900,
        "env_var": "STRIPE_PRICE_PRO_MONTHLY",
    },
    {
        "product_id": "etoh_business_monthly",
        "name": "EtOH Business",
        "description": "EtOH Business — 49€/mois, 800 crédits inclus, RAG illimité + multi-langues + CRM avancé.",
        "lookup_key": "etoh_business_monthly_eur_v1",
        "unit_amount": 4900,
        "env_var": "STRIPE_PRICE_BUSINESS_MONTHLY",
    },
    {
        "product_id": "etoh_premium_monthly",
        "name": "EtOH Premium",
        "description": "EtOH Premium — 99€/mois, 2000 crédits inclus, white-label + équipes + intégrations.",
        "lookup_key": "etoh_premium_monthly_eur_v1",
        "unit_amount": 9900,
        "env_var": "STRIPE_PRICE_PREMIUM_MONTHLY",
    },
]


def get_or_create_product(product_id: str, name: str, description: str):
    try:
        product = stripe.Product.retrieve(product_id)
        # keep name/desc in sync if they drifted
        if product.get("name") != name or product.get("description") != description:
            product = stripe.Product.modify(product_id, name=name, description=description)
        print(f"[reuse]   product {product_id}")
        return product
    except stripe.error.InvalidRequestError:
        product = stripe.Product.create(
            id=product_id, name=name, description=description, active=True
        )
        print(f"[create]  product {product_id}")
        return product


def get_or_create_price(product_id: str, lookup_key: str, unit_amount: int):
    prices = stripe.Price.list(lookup_keys=[lookup_key], limit=1)
    if prices.data:
        print(f"[reuse]   price   {lookup_key} -> {prices.data[0].id}")
        return prices.data[0]
    price = stripe.Price.create(
        unit_amount=unit_amount,
        currency="eur",
        recurring={"interval": "month"},
        product=product_id,
        lookup_key=lookup_key,
        nickname=lookup_key,
    )
    print(f"[create]  price   {lookup_key} -> {price.id}")
    return price


def main():
    print(f"Stripe mode: {'TEST' if STRIPE_SECRET_KEY.startswith('sk_test_') else 'LIVE'}")
    env_lines = []
    for cfg in PRODUCTS:
        product = get_or_create_product(cfg["product_id"], cfg["name"], cfg["description"])
        price = get_or_create_price(product.id, cfg["lookup_key"], cfg["unit_amount"])
        env_lines.append(f"{cfg['env_var']}={price.id}")

    print("\n--- Append these lines to backend/.env ---")
    for line in env_lines:
        print(line)
    print("------------------------------------------\n")


if __name__ == "__main__":
    main()
