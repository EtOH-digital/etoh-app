"""EtOH subscription plan configuration & helpers.

Single source of truth for tiers, pricing, included monthly credits and
feature flags. Used by both subscription endpoints and the feature-gating
helper. Stripe Price IDs are populated by `scripts/seed_stripe_subscriptions.py`
into env vars (STRIPE_PRICE_PRO_MONTHLY, _BUSINESS_, _PREMIUM_).
"""

from __future__ import annotations

import os
from typing import Dict, Any, Optional

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_BUSINESS = "business"
PLAN_PREMIUM = "premium"

# Order matters for UI rendering.
PLANS: list[dict] = [
    {
        "id": PLAN_FREE,
        "name": "Free",
        "tagline": "Pour découvrir EtOH",
        "price_eur": 0,
        "stripe_price_env": None,  # local only
        "credits_monthly": 20,
        "features": {
            "hub_public": False,
            "hub_chat_public": False,
            "rag": False,
            "rag_max_docs": 0,
            "multi_lang_outputs": False,
            "crm_advanced": False,
            "white_label": False,
            "team_seats": 1,
        },
        "feature_lines": [
            "1 Hub privé",
            "20 crédits / mois",
            "Coach IA basique",
            "Pas de chat public",
        ],
    },
    {
        "id": PLAN_PRO,
        "name": "Pro",
        "tagline": "Pour les vignerons indépendants",
        "price_eur": 19,
        "stripe_price_env": "STRIPE_PRICE_PRO_MONTHLY",
        "credits_monthly": 300,
        "features": {
            "hub_public": True,
            "hub_chat_public": True,
            "rag": True,
            "rag_max_docs": 5,
            "multi_lang_outputs": False,
            "crm_advanced": False,
            "white_label": False,
            "team_seats": 1,
        },
        "feature_lines": [
            "Hub public avec QR code",
            "300 crédits / mois",
            "Chat IA public",
            "RAG : 5 documents",
            "CRM Pilot complet",
        ],
    },
    {
        "id": PLAN_BUSINESS,
        "name": "Business",
        "tagline": "Pour les domaines en croissance",
        "price_eur": 49,
        "stripe_price_env": "STRIPE_PRICE_BUSINESS_MONTHLY",
        "credits_monthly": 800,
        "features": {
            "hub_public": True,
            "hub_chat_public": True,
            "rag": True,
            "rag_max_docs": -1,  # unlimited
            "multi_lang_outputs": True,
            "crm_advanced": True,
            "white_label": False,
            "team_seats": 3,
        },
        "feature_lines": [
            "Tout du plan Pro",
            "800 crédits / mois",
            "RAG illimité",
            "Sorties IA multi-langues",
            "CRM avancé",
            "3 sièges d'équipe",
        ],
    },
    {
        "id": PLAN_PREMIUM,
        "name": "Premium",
        "tagline": "Pour les maisons et distributeurs",
        "price_eur": 99,
        "stripe_price_env": "STRIPE_PRICE_PREMIUM_MONTHLY",
        "credits_monthly": 2000,
        "features": {
            "hub_public": True,
            "hub_chat_public": True,
            "rag": True,
            "rag_max_docs": -1,
            "multi_lang_outputs": True,
            "crm_advanced": True,
            "white_label": True,
            "team_seats": 10,
        },
        "feature_lines": [
            "Tout du plan Business",
            "2000 crédits / mois",
            "White-label",
            "Intégrations API",
            "10 sièges d'équipe",
            "Support prioritaire",
        ],
    },
]

PLAN_BY_ID: Dict[str, dict] = {p["id"]: p for p in PLANS}


def get_stripe_price_id(plan_id: str) -> Optional[str]:
    """Return the Stripe Price ID for a plan, or None for the free tier / missing env."""
    plan = PLAN_BY_ID.get(plan_id)
    if not plan or not plan.get("stripe_price_env"):
        return None
    return os.environ.get(plan["stripe_price_env"])


def get_effective_plan(user: Dict[str, Any]) -> str:
    """Compute the user's effective plan (free if no active subscription)."""
    sub = (user or {}).get("subscription") or {}
    plan_id = sub.get("plan_id") or PLAN_FREE
    status = sub.get("status") or "inactive"
    if plan_id == PLAN_FREE:
        return PLAN_FREE
    if status not in ("active", "trialing"):
        return PLAN_FREE
    return plan_id


def get_features(user: Dict[str, Any]) -> Dict[str, Any]:
    """Return {plan, features{...}, credits_monthly} for the given user."""
    plan_id = get_effective_plan(user)
    plan = PLAN_BY_ID.get(plan_id, PLAN_BY_ID[PLAN_FREE])
    return {
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "credits_monthly": plan["credits_monthly"],
        "features": plan["features"],
    }


def get_credits_for_plan(plan_id: str) -> int:
    plan = PLAN_BY_ID.get(plan_id)
    return int(plan["credits_monthly"]) if plan else 0
