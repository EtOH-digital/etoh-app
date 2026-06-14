"""
EtOH backend — AI Commercial Director for wines & spirits.

Modules:
  - /api/auth/*    : Google (Emergent) + Email/Password JWT auth
  - /api/coach/*   : AI business advisor (multi-turn conversation)
  - /api/studio/*  : AI content generation (LinkedIn, emails, etc.)
  - /api/pilot/*   : AI prospecting plans & target lists
  - /api/home/*    : Top 3 weekly recommended actions
  - /api/profile/* : Business profile CRUD
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
import hmac
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal, Annotated

import httpx
import jwt
from passlib.hash import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, status, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, EmailStr, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---------------------------------------------------------------------------
# Sentry — initialise BEFORE FastAPI() so middleware integration kicks in.
# ---------------------------------------------------------------------------
from core.sentry_init import init_sentry  # noqa: E402
SENTRY_ENABLED = init_sentry()

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXP_MINUTES = int(os.environ.get("JWT_EXP_MINUTES", "10080"))

LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4o-mini"

# --- Credits & pricing ---
INITIAL_FREE_CREDITS = 100
CREDIT_PRICE_EUR = 0.099
ACTION_COST = 1  # credits per outbound action (email / whatsapp / linkedin)

# --- Resend (email) configuration (MOCKED until DNS + API key are provided) ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "noreply@pilot.etoh.fr")
RESEND_FROM_NAME = os.environ.get("RESEND_FROM_NAME", "EtOH Pilot")

# --- Tavily (web search for Coach veille concurrentielle) ---
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# --- Stripe (wallet credit packs) ---
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

import stripe  # noqa: E402
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# Credit packs — (id, credits, price_eur, label)
CREDIT_PACKS = [
    {"id": "starter", "credits": 100, "price_eur": 9.90, "label": "Découverte"},
    {"id": "growth",  "credits": 500, "price_eur": 49.50, "label": "Régulier"},
    {"id": "pro",     "credits": 2000, "price_eur": 178.20, "label": "Pro · -10%"},
]
PACK_BY_ID = {p["id"]: p for p in CREDIT_PACKS}

EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("etoh")

# Re-init Sentry now that logging is configured, so we get the confirmation log line.
if SENTRY_ENABLED:
    logger.info("Sentry monitoring active.")

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client[DB_NAME]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionIn(BaseModel):
    session_token: str


class UserOut(BaseModel):
    user_id: str
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None
    providers: List[str] = []
    business_profile: Optional[Dict[str, Any]] = None
    credits: int = 0


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BusinessProfileIn(BaseModel):
    business_name: Optional[str] = None
    business_type: Optional[Literal["winery", "cooperative", "merchant", "spirits", "brewery", "distillery", "wine_shop", "restaurant", "importer", "distributor", "other"]] = None
    region: Optional[str] = None
    main_products: Optional[str] = None
    role: Optional[str] = None
    language: Optional[Literal["fr", "en"]] = "fr"
    # Customizable weekly sprint goals (per user)
    goal_prospects: Optional[int] = Field(default=None, ge=1, le=500)
    goal_campaigns: Optional[int] = Field(default=None, ge=1, le=100)
    goal_distributors: Optional[int] = Field(default=None, ge=1, le=100)
    goal_markets: Optional[int] = Field(default=None, ge=1, le=20)
    # Onboarding data
    revenue: Optional[str] = None            # < 100k, 100k-500k, 500k-2M, 2M-10M, +10M
    objectives: Optional[List[str]] = None   # multi-select objectives
    products: Optional[List[str]] = None     # vins rouges, bières, etc.
    avg_bottle_price: Optional[str] = None
    avg_case_price: Optional[str] = None
    target_countries: Optional[List[str]] = None
    target_channels: Optional[List[str]] = None
    onboarded: Optional[bool] = None
    # Brand voice (generated after onboarding, editable)
    brand_voice_tone: Optional[List[str]] = None        # ["professionnel","expert","accessible"]
    brand_voice_personality: Optional[List[str]] = None # ["passionnée","authentique","pédagogique"]
    brand_voice_style: Optional[List[str]] = None       # ["phrases courtes","storytelling"]
    brand_voice_languages: Optional[List[str]] = None   # ["fr","en"]
    brand_voice_sources: Optional[List[str]] = None     # URLs / domain names trained on


class CoachMessageIn(BaseModel):
    session_id: Optional[str] = None
    message: str
    language: Literal["fr", "en"] = "fr"


class StudioRequestIn(BaseModel):
    template: Literal[
        "linkedin_post",
        "email_campaign",
        "sales_message",
        "product_description",
        "trade_show_followup",
        "commercial_presentation",
    ]
    brief: str
    tone: Optional[Literal["professional", "warm", "premium", "casual"]] = "professional"
    language: Literal["fr", "en"] = "fr"


class PilotRequestIn(BaseModel):
    target_type: Literal["restaurants", "importers", "distributors", "wine_shops", "other"]
    region: str
    product_focus: Optional[str] = None
    language: Literal["fr", "en"] = "fr"


class HomeRecommendationsIn(BaseModel):
    language: Literal["fr", "en"] = "fr"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


def _create_jwt(user_id: str, email: str) -> str:
    now = _now()
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXP_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _serialize_user(doc: Dict[str, Any]) -> UserOut:
    return UserOut(
        user_id=doc["user_id"],
        email=doc["email"],
        name=doc.get("name"),
        picture=doc.get("picture"),
        providers=doc.get("providers", []),
        business_profile=doc.get("business_profile"),
        credits=int(doc.get("credits", 0)),
    )


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()

    # Try JWT first
    user_id: Optional[str] = None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        # Not a JWT — treat as Google session_token
        session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Normalize expires_at
        exp = session.get("expires_at")
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp < _now():
            raise HTTPException(status_code=401, detail="Session expired")
        user_id = session.get("user_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_COACH_FR = """Tu es **EtOH Coach**, Directeur Commercial IA spécialisé en vins et spiritueux.
Tu aides des producteurs (vignerons, caves, coopératives, négociants, distillateurs) à VENDRE PLUS.

Style de réponse :
- Concis, structuré, orienté action.
- Toujours en français.
- Format Markdown : titres `##`, listes à puces, gras pour les points clés.
- Quand on te pose une question business, structure ta réponse en 3 blocs :
  1. **Diagnostic** (2-3 phrases)
  2. **Recommandations** (3 à 5 points concrets)
  3. **Plan d'action priorisé** (3 étapes avec délais réalistes)
- Pas de blabla, pas de disclaimers. Tu es un directeur commercial senior, pas un assistant générique."""

SYSTEM_PROMPT_COACH_EN = """You are **EtOH Coach**, the AI Commercial Director for wines & spirits.
You help producers (wineries, cooperatives, merchants, distillers) SELL MORE.

Response style:
- Concise, structured, action-oriented.
- Always in English.
- Markdown format: `##` headings, bullet lists, bold for key points.
- For business questions, structure your answer in 3 blocks:
  1. **Diagnosis** (2-3 sentences)
  2. **Recommendations** (3 to 5 concrete points)
  3. **Prioritized action plan** (3 steps with realistic deadlines)
- No fluff, no disclaimers. You are a senior commercial director, not a generic assistant."""

SYSTEM_PROMPT_STUDIO_FR = """Tu es **EtOH Studio**, rédacteur commercial IA pour le secteur des vins et spiritueux.
Tu produis des contenus commerciaux prêts à publier (LinkedIn, emails, fiches produits, présentations).
Style : élégant, premium, jamais cliché. Pas d'emojis sauf 1 maximum dans LinkedIn.
Toujours en français. Format Markdown.
Sors UNIQUEMENT le contenu demandé, sans préambule."""

SYSTEM_PROMPT_STUDIO_EN = """You are **EtOH Studio**, AI commercial copywriter for wines & spirits.
Produce publish-ready commercial content (LinkedIn, emails, product sheets, presentations).
Style: elegant, premium, never cliché. No emojis except 1 max in LinkedIn.
Always in English. Markdown format.
Output ONLY the requested content, no preamble."""

SYSTEM_PROMPT_PILOT_FR = """Tu es **EtOH Pilot**, expert IA en exécution commerciale pour vins et spiritueux.
Tu génères des plans de prospection actionnables : listes de cibles, étapes, scripts d'approche.
Toujours en français. Format Markdown structuré. Données réalistes mais clairement marquées comme suggestions à valider."""

SYSTEM_PROMPT_PILOT_EN = """You are **EtOH Pilot**, AI commercial execution expert for wines & spirits.
You generate actionable prospecting plans: target lists, steps, approach scripts.
Always in English. Structured Markdown format. Realistic data but clearly flagged as suggestions to validate."""


def _coach_system(lang: str) -> str:
    return SYSTEM_PROMPT_COACH_FR if lang == "fr" else SYSTEM_PROMPT_COACH_EN


def _studio_system(lang: str) -> str:
    return SYSTEM_PROMPT_STUDIO_FR if lang == "fr" else SYSTEM_PROMPT_STUDIO_EN


def _pilot_system(lang: str) -> str:
    return SYSTEM_PROMPT_PILOT_FR if lang == "fr" else SYSTEM_PROMPT_PILOT_EN


def _brand_voice_block(bp: Dict[str, Any], lang: str) -> str:
    """Builds an inline Brand Voice section to inject into Studio / Pilot draft prompts."""
    tone = bp.get("brand_voice_tone") or []
    pers = bp.get("brand_voice_personality") or []
    style = bp.get("brand_voice_style") or []
    if not (tone or pers or style):
        return ""
    if lang == "fr":
        return (
            "\n\n--- BRAND VOICE (à respecter strictement) ---\n"
            f"- Ton : {', '.join(tone) or 'professionnel'}\n"
            f"- Personnalité : {', '.join(pers) or 'authentique'}\n"
            f"- Style d'écriture : {', '.join(style) or 'phrases courtes'}\n"
            "Réponds avec ce ton, cette personnalité et ce style.\n"
        )
    return (
        "\n\n--- BRAND VOICE (strictly follow) ---\n"
        f"- Tone: {', '.join(tone) or 'professional'}\n"
        f"- Personality: {', '.join(pers) or 'authentic'}\n"
        f"- Writing style: {', '.join(style) or 'short sentences'}\n"
        "Reply using this tone, personality and style.\n"
    )


def _make_chat(session_id: str, system_message: str) -> LlmChat:
    return LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=session_id,
        system_message=system_message,
    ).with_model(LLM_PROVIDER, LLM_MODEL)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="EtOH API", version="1.0.0")
api = APIRouter(prefix="/api")

# ---- Rate limiter (anti-abuse on LLM + auth endpoints) ----
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi import Request

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rl_handler(_request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


# ---- In-memory per-user rate limiter for LLM endpoints ----
from collections import defaultdict, deque
import time as _time

_USER_HITS: Dict[str, deque] = defaultdict(deque)


def llm_rate_limit(max_per_minute: int = 20):
    """Per-user rate limiter (sliding 60s window). Use as a FastAPI Depends.

    Default cap: 20 LLM calls / user / minute — enough for fast typing,
    blocks scripted abuse. Increase to 40 for very cheap endpoints.
    """

    async def _dep(current_user: Dict[str, Any] = Depends(get_current_user)):
        uid = current_user["user_id"]
        now = _time.time()
        dq = _USER_HITS[uid]
        # drop old hits
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= max_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Trop de requêtes IA — patientez quelques secondes (limite: {max_per_minute}/min).",
            )
        dq.append(now)
        return current_user

    return _dep


@api.get("/")
async def root():
    return {"name": "EtOH API", "status": "ok"}


# ---------- Stripe webhook (signed) ----------
@app.post("/api/wallet/webhook")
@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe-signed webhook to credit users after successful checkout.

    Mounted at both `/api/wallet/webhook` (legacy) and `/api/stripe/webhook` (canonical).
    Configure your Stripe Dashboard endpoint to point to `/api/stripe/webhook`.
    Handles `checkout.session.completed` and `payment_intent.payment_failed`.
    Idempotency: each Stripe event id is stored in `stripe_events` (unique index).
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            # Fallback for dev environments without a webhook secret configured.
            import json as _json
            event = _json.loads(payload.decode("utf-8"))
            logging.warning("STRIPE_WEBHOOK_SECRET not set — webhook signature NOT verified.")
    except Exception as e:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"invalid webhook signature: {e}")

    # --- Idempotency: have we already processed this Stripe event? ---
    event_id = (event.get("id") if isinstance(event, dict) else None) or None
    if event_id:
        try:
            await db.stripe_events.insert_one({
                "event_id": event_id,
                "type": event.get("type"),
                "received_at": _now(),
            })
        except DuplicateKeyError:
            # Already processed → short-circuit. Any *other* DB error must surface
            # (so Sentry catches real outages instead of pretending they were replays).
            return {"received": True, "duplicate": True}

    etype = event.get("type") if isinstance(event, dict) else event["type"]
    data_obj = (event.get("data") or {}).get("object") if isinstance(event, dict) else event["data"]["object"]

    if etype == "checkout.session.completed":
        session = data_obj
        meta = (session.get("metadata") or {}) if isinstance(session, dict) else {}
        user_id = meta.get("user_id")
        pack_id = meta.get("pack_id")
        if user_id and pack_id and pack_id in PACK_BY_ID:
            pack = PACK_BY_ID[pack_id]
            now = _now()
            sid = session.get("id") if isinstance(session, dict) else None
            # Belt-and-suspenders: also check wallet_events (legacy idempotency).
            existing = await db.wallet_events.find_one({"stripe_session_id": sid}) if sid else None
            if not existing:
                await db.users.update_one(
                    {"user_id": user_id},
                    {"$inc": {"credits": pack["credits"]}},
                )
                # Also mark the wallet_checkout row paid if present
                if sid:
                    await db.wallet_checkouts.update_one(
                        {"session_id": sid},
                        {"$set": {"status": "paid", "paid_at": now}},
                    )
                await db.wallet_events.insert_one(
                    {
                        "id": f"evt_{uuid.uuid4().hex[:10]}",
                        "user_id": user_id,
                        "pack_id": pack_id,
                        "credits": pack["credits"],
                        "amount_eur": pack["price_eur"],
                        "stripe_session_id": sid,
                        "stripe_event_id": event_id,
                        "source": "webhook",
                        "created_at": now,
                    }
                )
                logger.info(f"Stripe webhook → +{pack['credits']} credits for {user_id}")
    elif etype == "payment_intent.payment_failed":
        pi = data_obj if isinstance(data_obj, dict) else {}
        err = (pi.get("last_payment_error") or {}) if isinstance(pi, dict) else {}
        logger.warning(
            "Stripe payment failed pi=%s code=%s msg=%s",
            pi.get("id"), err.get("code"), err.get("message"),
        )
        if event_id:
            await db.stripe_events.update_one(
                {"event_id": event_id},
                {"$set": {
                    "payment_intent_id": pi.get("id"),
                    "failure_code": err.get("code"),
                    "failure_message": err.get("message"),
                    "handled_at": _now(),
                }},
            )

    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        await _handle_subscription_upsert(data_obj)
    elif etype == "customer.subscription.deleted":
        await _handle_subscription_deleted(data_obj)
    elif etype == "invoice.paid":
        await _handle_invoice_paid(data_obj)

    return {"received": True}


# ---------------------------------------------------------------------------
# Subscription helpers (called from webhook + REST endpoints below)
# ---------------------------------------------------------------------------
from core.subscriptions import (  # noqa: E402
    PLANS,
    PLAN_BY_ID,
    PLAN_FREE,
    get_effective_plan,
    get_features,
    get_credits_for_plan,
    get_stripe_price_id,
)


def _plan_id_from_price(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    for plan in PLANS:
        if get_stripe_price_id(plan["id"]) == price_id:
            return plan["id"]
    return None


async def _handle_subscription_upsert(sub: Dict[str, Any]) -> None:
    """Persist customer.subscription.created/.updated on the user record."""
    if not isinstance(sub, dict):
        return
    customer_id = sub.get("customer")
    sub_id = sub.get("id")
    status_ = sub.get("status")
    period_end_ts = sub.get("current_period_end")
    current_period_end = (
        datetime.fromtimestamp(period_end_ts, tz=timezone.utc) if period_end_ts else None
    )
    items = ((sub.get("items") or {}).get("data") or [])
    price_id = items[0].get("price", {}).get("id") if items else None
    plan_id = _plan_id_from_price(price_id)
    if plan_id is None:
        logger.warning("Subscription %s for customer %s uses unknown price_id=%s", sub_id, customer_id, price_id)
        return

    user_doc = await db.users.find_one({"subscription.stripe_customer_id": customer_id})
    if not user_doc:
        # Best-effort: try metadata fallback (Checkout sets app_user_id)
        meta_uid = (sub.get("metadata") or {}).get("app_user_id")
        if meta_uid:
            user_doc = await db.users.find_one({"user_id": meta_uid})
            if user_doc:
                await db.users.update_one(
                    {"user_id": meta_uid},
                    {"$set": {"subscription.stripe_customer_id": customer_id}},
                )
    if not user_doc:
        logger.warning("Subscription event with unknown customer_id=%s", customer_id)
        return

    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {"$set": {
            "subscription.plan_id": plan_id,
            "subscription.stripe_customer_id": customer_id,
            "subscription.stripe_subscription_id": sub_id,
            "subscription.status": status_,
            "subscription.current_period_end": current_period_end,
            "subscription.cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
            "subscription.updated_at": _now(),
        }},
    )
    logger.info("Subscription upsert: user=%s plan=%s status=%s", user_doc["user_id"], plan_id, status_)


async def _handle_subscription_deleted(sub: Dict[str, Any]) -> None:
    if not isinstance(sub, dict):
        return
    customer_id = sub.get("customer")
    user_doc = await db.users.find_one({"subscription.stripe_customer_id": customer_id})
    if not user_doc:
        return
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {"$set": {
            "subscription.status": "canceled",
            "subscription.plan_id": PLAN_FREE,
            "subscription.cancel_at_period_end": False,
            "subscription.updated_at": _now(),
        }},
    )
    logger.info("Subscription canceled: user=%s", user_doc["user_id"])


async def _handle_invoice_paid(invoice: Dict[str, Any]) -> None:
    """Renew monthly credits idempotently via invoice.id."""
    if not isinstance(invoice, dict):
        return
    invoice_id = invoice.get("id")
    customer_id = invoice.get("customer")
    billing_reason = invoice.get("billing_reason")

    if not invoice_id:
        return
    # Idempotency on invoice id (separate from event id — Stripe may retry same invoice across events)
    try:
        await db.stripe_invoices.insert_one({
            "_id": invoice_id,
            "customer_id": customer_id,
            "billing_reason": billing_reason,
            "received_at": _now(),
        })
    except DuplicateKeyError:
        return

    # Only credit on subscription cycle / create — not on credit-pack invoices (which we already credit via session.completed)
    if billing_reason not in ("subscription_cycle", "subscription_create", "subscription_update"):
        return

    user_doc = await db.users.find_one({"subscription.stripe_customer_id": customer_id})
    if not user_doc:
        return
    plan_id = (user_doc.get("subscription") or {}).get("plan_id") or PLAN_FREE
    credits_to_add = get_credits_for_plan(plan_id)
    if credits_to_add <= 0:
        return
    await db.users.update_one(
        {"user_id": user_doc["user_id"]},
        {"$inc": {"credits": credits_to_add}},
    )
    await db.wallet_events.insert_one({
        "id": f"sub_{uuid.uuid4().hex[:10]}",
        "user_id": user_doc["user_id"],
        "plan_id": plan_id,
        "credits": credits_to_add,
        "stripe_invoice_id": invoice_id,
        "source": "subscription_renewal",
        "created_at": _now(),
    })
    logger.info("Subscription invoice paid → +%d credits to user=%s", credits_to_add, user_doc["user_id"])


@app.get("/api/debug/sentry")
async def debug_sentry():
    """Test endpoint — raises an exception to verify Sentry capture.

    Disabled in production: only available when SENTRY_ENVIRONMENT != 'production'
    OR when DEBUG_ENDPOINTS=1 is explicitly set.
    """
    if not SENTRY_ENABLED:
        return {"sentry": "disabled"}
    env = os.environ.get("SENTRY_ENVIRONMENT", "development").lower()
    debug_on = os.environ.get("DEBUG_ENDPOINTS", "").lower() in ("1", "true", "yes")
    if env == "production" and not debug_on:
        raise HTTPException(status_code=404, detail="not found")
    raise RuntimeError("Sentry test exception — if you see this in Sentry, monitoring works ✅")


# ---------------------------------------------------------------------------
# Subscription endpoints
# ---------------------------------------------------------------------------
class SubscriptionCheckoutIn(BaseModel):
    plan_id: str
    success_url: str
    cancel_url: str


async def _get_or_create_stripe_customer(user: Dict[str, Any]) -> str:
    sub = user.get("subscription") or {}
    cid = sub.get("stripe_customer_id")
    if cid:
        try:
            stripe.Customer.retrieve(cid)
            return cid
        except Exception:
            pass  # stale id → recreate
    customer = stripe.Customer.create(
        email=user.get("email"),
        name=user.get("name") or None,
        metadata={"app_user_id": user["user_id"]},
    )
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"subscription.stripe_customer_id": customer.id}},
    )
    return customer.id


@api.get("/subscription/plans")
async def list_subscription_plans():
    """Public — return all subscription tiers with feature lines for the pricing page."""
    out = []
    for plan in PLANS:
        out.append({
            "id": plan["id"],
            "name": plan["name"],
            "tagline": plan["tagline"],
            "price_eur": plan["price_eur"],
            "credits_monthly": plan["credits_monthly"],
            "features": plan["features"],
            "feature_lines": plan["feature_lines"],
            "stripe_configured": bool(get_stripe_price_id(plan["id"])) if plan["price_eur"] > 0 else True,
        })
    return {"plans": out}


@api.get("/subscription/me")
async def get_my_subscription(user=Depends(get_current_user)):
    user_doc = await db.users.find_one({"user_id": user["user_id"]})
    sub = (user_doc or {}).get("subscription") or {}
    feats = get_features(user_doc or {})
    return {
        "plan_id": feats["plan_id"],
        "plan_name": feats["plan_name"],
        "status": sub.get("status"),
        "current_period_end": sub.get("current_period_end"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        "stripe_customer_id": sub.get("stripe_customer_id"),
        "stripe_subscription_id": sub.get("stripe_subscription_id"),
        "credits_monthly": feats["credits_monthly"],
        "features": feats["features"],
    }


@api.post("/subscription/checkout")
async def create_subscription_checkout(payload: SubscriptionCheckoutIn, user=Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "stripe not configured")
    plan_id = payload.plan_id
    if plan_id == PLAN_FREE:
        raise HTTPException(400, "free plan does not require checkout")
    price_id = get_stripe_price_id(plan_id)
    if not price_id:
        raise HTTPException(400, f"plan '{plan_id}' has no Stripe price configured")

    user_doc = await db.users.find_one({"user_id": user["user_id"]})
    if not user_doc:
        raise HTTPException(401, "user not found")
    customer_id = await _get_or_create_stripe_customer(user_doc)

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
        allow_promotion_codes=True,
        metadata={
            "app_user_id": user["user_id"],
            "plan_id": plan_id,
            "checkout_type": "subscription",
        },
        subscription_data={
            "metadata": {
                "app_user_id": user["user_id"],
                "plan_id": plan_id,
            }
        },
    )
    return {"checkout_url": session.url, "session_id": session.id}


@api.post("/subscription/portal")
async def create_billing_portal(user=Depends(get_current_user)):
    """Stripe Billing Portal session for self-service cancel/upgrade/update PM."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "stripe not configured")
    user_doc = await db.users.find_one({"user_id": user["user_id"]})
    sub = (user_doc or {}).get("subscription") or {}
    cid = sub.get("stripe_customer_id")
    if not cid:
        raise HTTPException(400, "no Stripe customer for this user — subscribe first")
    return_url = os.environ.get("FRONTEND_BASE_URL", "https://app.etoh.io") + "/subscription"
    portal = stripe.billing_portal.Session.create(customer=cid, return_url=return_url)
    return {"portal_url": portal.url}


@api.get("/features/me")
async def get_my_features(user=Depends(get_current_user)):
    user_doc = await db.users.find_one({"user_id": user["user_id"]})
    return get_features(user_doc or {})


# ---------------------------------------------------------------------------
# Admin API (X-Admin-Key header) — for etoh.io/studio/admin back-office
# ---------------------------------------------------------------------------
ETOH_ADMIN_API_KEY = os.environ.get("ETOH_ADMIN_API_KEY", "")


async def require_admin_key(request: Request) -> None:
    """FastAPI dependency: validates the X-Admin-Key header.

    Use as: ` _: None = Depends(require_admin_key)` on any admin-only route.
    Returns 401 if missing, 403 if mismatch, 503 if admin not configured.
    """
    if not ETOH_ADMIN_API_KEY:
        raise HTTPException(503, "admin api not configured")
    provided = request.headers.get("x-admin-key") or request.headers.get("X-Admin-Key")
    if not provided:
        raise HTTPException(401, "missing X-Admin-Key header")
    if not hmac.compare_digest(provided, ETOH_ADMIN_API_KEY):
        raise HTTPException(403, "invalid admin key")


@api.get("/admin/health")
async def admin_health(_: None = Depends(require_admin_key)):
    """Sanity-check endpoint for the admin back-office — proves the key works."""
    return {"ok": True, "service": "etoh-api", "ts": _now().isoformat()}


@api.get("/admin/metrics/summary")
async def admin_metrics_summary(_: None = Depends(require_admin_key)):
    """Aggregated metrics for the admin dashboard (`etoh.io/studio/admin`).

    Returns: users count, active subscriptions, MRR estimate, total credits consumed,
    Hub items count, public Hub views, LLM events 30d.
    """
    users_count = await db.users.count_documents({})
    active_subs = await db.users.count_documents({"subscription.status": {"$in": ["active", "trialing"]}})
    hub_items = await db.hub_items.count_documents({})
    # MRR: sum credits_monthly€ × active subs per plan
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
    # Signups last 30 days
    since = _now() - timedelta(days=30)
    signups_30d = await db.users.count_documents({"created_at": {"$gte": since}})
    # Credits spent (wallet_events with negative or via llm_events if any)
    llm_events_30d = 0
    try:
        llm_events_30d = await db.llm_events.count_documents({"created_at": {"$gte": since}})
    except Exception:
        pass
    # Public hub views
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


@api.post("/admin/users/{user_id}/credits")
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


# ---------- Auth ----------
@api.post("/auth/signup", response_model=TokenOut)
async def signup(payload: SignupIn):
    existing = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if existing and "password_hash" in existing:
        raise HTTPException(status_code=400, detail="Account already exists. Please log in.")

    password_hash = bcrypt.hash(payload.password)

    if existing:
        # Add password auth to Google-only user
        providers = list(set(existing.get("providers", []) + ["password"]))
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {"password_hash": password_hash, "providers": providers,
                      "name": payload.name or existing.get("name")}},
        )
        user = await db.users.find_one({"user_id": existing["user_id"]}, {"_id": 0})
    else:
        user_id = _new_user_id()
        doc = {
            "user_id": user_id,
            "email": payload.email.lower(),
            "name": payload.name,
            "password_hash": password_hash,
            "providers": ["password"],
            "business_profile": {"language": "fr"},
            "credits": INITIAL_FREE_CREDITS,
            "created_at": _now(),
        }
        await db.users.insert_one(doc)
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0})

    token = _create_jwt(user["user_id"], user["email"])
    return TokenOut(access_token=token, user=_serialize_user(user))


@api.post("/auth/login", response_model=TokenOut)
async def login(payload: LoginIn):
    user = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not user or "password_hash" not in user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
    if not bcrypt.verify(payload.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    token = _create_jwt(user["user_id"], user["email"])
    return TokenOut(access_token=token, user=_serialize_user(user))


@api.post("/auth/google/session", response_model=TokenOut)
async def google_session(payload: GoogleSessionIn):
    """Frontend sends the session_id returned by Emergent OAuth. Backend verifies it."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            EMERGENT_SESSION_API,
            headers={"X-Session-ID": payload.session_token},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google session")
    data = r.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="No email returned by Google")

    name = data.get("name")
    picture = data.get("picture")
    real_session_token = data.get("session_token")

    # Upsert user
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        providers = list(set(existing.get("providers", []) + ["google"]))
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {"name": name or existing.get("name"),
                      "picture": picture or existing.get("picture"),
                      "providers": providers}},
        )
        user_id = existing["user_id"]
    else:
        user_id = _new_user_id()
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "providers": ["google"],
            "business_profile": {"language": "fr"},
            "credits": INITIAL_FREE_CREDITS,
            "created_at": _now(),
        })

    # Store session
    expires_at = _now() + timedelta(days=7)
    await db.user_sessions.update_one(
        {"session_token": real_session_token},
        {"$set": {
            "session_token": real_session_token,
            "user_id": user_id,
            "expires_at": expires_at,
            "created_at": _now(),
        }},
        upsert=True,
    )

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    # Return Emergent's session_token as access_token (bearer)
    return TokenOut(access_token=real_session_token, user=_serialize_user(user))


@api.get("/auth/me", response_model=UserOut)
async def me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return _serialize_user(current_user)


@api.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}


# ---------- Profile ----------
@api.put("/profile", response_model=UserOut)
async def update_profile(payload: BusinessProfileIn,
                         current_user: Dict[str, Any] = Depends(get_current_user)):
    update = {f"business_profile.{k}": v for k, v in payload.model_dump(exclude_none=True).items()}
    await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": update})
    user = await db.users.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    return _serialize_user(user)


# ---------- Home: Top 3 actions ----------
@api.post("/home/recommendations")
async def home_recommendations(payload: HomeRecommendationsIn,
                               current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generates 3 personalized weekly actions based on business profile."""
    bp = current_user.get("business_profile") or {}
    lang = payload.language

    business_ctx_fr = (
        f"Profil utilisateur :\n"
        f"- Entreprise : {bp.get('business_name') or 'non renseignée'}\n"
        f"- Type : {bp.get('business_type') or 'non renseigné'}\n"
        f"- Région : {bp.get('region') or 'non renseignée'}\n"
        f"- Produits : {bp.get('main_products') or 'vins / spiritueux'}\n"
        f"- Rôle : {bp.get('role') or 'dirigeant'}\n"
    )
    business_ctx_en = (
        f"User profile:\n"
        f"- Business: {bp.get('business_name') or 'unspecified'}\n"
        f"- Type: {bp.get('business_type') or 'unspecified'}\n"
        f"- Region: {bp.get('region') or 'unspecified'}\n"
        f"- Products: {bp.get('main_products') or 'wines / spirits'}\n"
        f"- Role: {bp.get('role') or 'owner'}\n"
    )

    instruction_fr = f"""{business_ctx_fr}

Génère **exactement 3 actions commerciales prioritaires pour cette semaine**.
Renvoie UNIQUEMENT un JSON valide (sans markdown, sans ``` ```), tableau de 3 objets, chaque objet a:
- "title": titre court de 4-7 mots (ex: "Contacter 5 cavistes lyonnais")
- "description": 1 phrase actionnable (max 20 mots)
- "module": un de "coach", "studio", "pilot"
- "icon": un emoji approprié

Exemple de format:
[{{"title": "...","description": "...","module": "coach","icon": "🍷"}}]"""

    instruction_en = f"""{business_ctx_en}

Generate **exactly 3 priority commercial actions for this week**.
Return ONLY valid JSON (no markdown, no ``` ```), array of 3 objects, each with:
- "title": short title 4-7 words (e.g. "Contact 5 Lyon wine shops")
- "description": 1 actionable sentence (max 20 words)
- "module": one of "coach", "studio", "pilot"
- "icon": appropriate emoji

Format example:
[{{"title": "...","description": "...","module": "coach","icon": "🍷"}}]"""

    chat = _make_chat(
        session_id=f"home_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_coach_system(lang),
    )
    text = await chat.send_message(UserMessage(text=instruction_fr if lang == "fr" else instruction_en))

    # Parse JSON
    import json, re
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        recs = json.loads(cleaned)
        if not isinstance(recs, list):
            raise ValueError("not a list")
    except Exception:
        # Fallback static suggestions
        recs = [
            {"title": "Contacter des cavistes locaux" if lang == "fr" else "Contact local wine shops",
             "description": "Identifie 5 cavistes proches et propose une dégustation." if lang == "fr"
                            else "Identify 5 nearby wine shops and offer a tasting.",
             "module": "pilot", "icon": "🍷"},
            {"title": "Publier un post LinkedIn" if lang == "fr" else "Publish a LinkedIn post",
             "description": "Mettre en avant ton dernier millésime auprès de ton réseau." if lang == "fr"
                            else "Showcase your latest vintage to your network.",
             "module": "studio", "icon": "📣"},
            {"title": "Préparer la prochaine campagne" if lang == "fr" else "Plan your next campaign",
             "description": "Pose-toi avec Coach pour cadrer ta stratégie du mois." if lang == "fr"
                            else "Sit with Coach to frame this month's strategy.",
             "module": "coach", "icon": "🎯"},
        ]
    return {"recommendations": recs[:3]}


# ---------- Coach ----------
@api.post("/coach/message")
async def coach_message(payload: CoachMessageIn,
                        current_user: Dict[str, Any] = Depends(llm_rate_limit(30))):
    session_id = payload.session_id or f"coach_{current_user['user_id']}_{uuid.uuid4().hex[:8]}"

    # Load prior history for this session
    history_doc = await db.coach_conversations.find_one(
        {"session_id": session_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    messages: List[Dict[str, str]] = (history_doc or {}).get("messages", [])

    chat = _make_chat(session_id=session_id, system_message=_coach_system(payload.language))

    # Replay prior turns into LlmChat (in-memory)
    for m in messages:
        if m["role"] == "user":
            await chat.send_message(UserMessage(text=m["content"]))
            # Note: replaying via send_message consumes API calls; in MVP we keep
            # conversation state inside the LlmChat for this request only by
            # rebuilding from history. For best performance, skip replay and
            # instead pass concatenated context. Here we simplify by NOT replaying:
            break

    # Simpler approach: include short recent history in the user message itself
    history_text = ""
    if messages:
        recent = messages[-6:]  # last 3 turns
        history_text = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent)
        history_text = f"Historique récent :\n{history_text}\n\n---\n\n"

    # New chat instance without replay (simpler, deterministic)
    chat = _make_chat(session_id=session_id, system_message=_coach_system(payload.language))
    full_user_text = (history_text + payload.message) if history_text else payload.message
    reply = await chat.send_message(UserMessage(text=full_user_text))

    # Persist
    new_messages = messages + [
        {"role": "user", "content": payload.message, "ts": _now().isoformat()},
        {"role": "assistant", "content": reply, "ts": _now().isoformat()},
    ]
    await db.coach_conversations.update_one(
        {"session_id": session_id, "user_id": current_user["user_id"]},
        {"$set": {
            "session_id": session_id,
            "user_id": current_user["user_id"],
            "messages": new_messages,
            "updated_at": _now(),
        }},
        upsert=True,
    )
    return {"session_id": session_id, "reply": reply}


@api.get("/coach/sessions")
async def coach_sessions(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.coach_conversations.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("updated_at", -1).limit(30)
    items = []
    async for c in cursor:
        msgs = c.get("messages", [])
        first_user = next((m["content"] for m in msgs if m["role"] == "user"), "Nouvelle conversation")
        items.append({
            "session_id": c["session_id"],
            "title": first_user[:60],
            "updated_at": (c.get("updated_at") or _now()).isoformat() if isinstance(c.get("updated_at"), datetime) else c.get("updated_at"),
            "message_count": len(msgs),
        })
    return {"sessions": items}


@api.get("/coach/sessions/{session_id}")
async def coach_session_detail(session_id: str,
                               current_user: Dict[str, Any] = Depends(get_current_user)):
    c = await db.coach_conversations.find_one(
        {"session_id": session_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not c:
        raise HTTPException(status_code=404, detail="Session not found")
    return c


# ---------- Studio ----------
TEMPLATE_PROMPTS_FR = {
    "linkedin_post": "Rédige un post LinkedIn engageant (180-250 mots) avec un hook fort, 3 paragraphes courts, et une question d'engagement à la fin.",
    "email_campaign": "Rédige un email de campagne commerciale : objet accrocheur (max 7 mots) + corps (150-200 mots) + CTA clair.",
    "sales_message": "Rédige un message de prospection commerciale court (80-120 mots) personnalisable, ton direct mais professionnel.",
    "product_description": "Rédige une description produit premium (120-180 mots) : nez, bouche, accords mets-vin, occasions.",
    "trade_show_followup": "Rédige un email de suivi post-salon (120-160 mots) : remercie, rappelle le contexte, propose 1 prochaine étape.",
    "commercial_presentation": "Rédige le script d'une présentation commerciale en 5 slides : titre + bullet points pour chaque slide.",
}
TEMPLATE_PROMPTS_EN = {
    "linkedin_post": "Write an engaging LinkedIn post (180-250 words) with a strong hook, 3 short paragraphs, and an engagement question at the end.",
    "email_campaign": "Write a commercial campaign email: catchy subject (max 7 words) + body (150-200 words) + clear CTA.",
    "sales_message": "Write a short commercial prospecting message (80-120 words), customizable, direct but professional tone.",
    "product_description": "Write a premium product description (120-180 words): nose, palate, food pairings, occasions.",
    "trade_show_followup": "Write a post-trade-show follow-up email (120-160 words): thank, recall context, propose 1 next step.",
    "commercial_presentation": "Write a 5-slide commercial presentation script: title + bullet points for each slide.",
}


@api.post("/studio/generate")
async def studio_generate(payload: StudioRequestIn,
                          current_user: Dict[str, Any] = Depends(llm_rate_limit(30))):
    bp = current_user.get("business_profile") or {}
    lang = payload.language
    template_instruction = TEMPLATE_PROMPTS_FR.get(payload.template) if lang == "fr" \
        else TEMPLATE_PROMPTS_EN.get(payload.template)

    business_ctx_fr = f"Entreprise: {bp.get('business_name') or '—'} | Région: {bp.get('region') or '—'} | Produits: {bp.get('main_products') or 'vins/spiritueux'}"
    business_ctx_en = f"Business: {bp.get('business_name') or '—'} | Region: {bp.get('region') or '—'} | Products: {bp.get('main_products') or 'wines/spirits'}"

    prompt_fr = f"""{business_ctx_fr}
Ton souhaité : {payload.tone}
Brief : {payload.brief}

Tâche : {template_instruction}"""
    prompt_en = f"""{business_ctx_en}
Desired tone: {payload.tone}
Brief: {payload.brief}

Task: {template_instruction}"""

    chat = _make_chat(
        session_id=f"studio_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_studio_system(lang) + _brand_voice_block(bp, lang),
    )
    content = await chat.send_message(UserMessage(text=prompt_fr if lang == "fr" else prompt_en))

    # Persist
    doc_id = f"studio_{uuid.uuid4().hex[:12]}"
    await db.studio_outputs.insert_one({
        "id": doc_id,
        "user_id": current_user["user_id"],
        "template": payload.template,
        "brief": payload.brief,
        "tone": payload.tone,
        "language": lang,
        "content": content,
        "created_at": _now(),
    })
    return {"id": doc_id, "template": payload.template, "content": content}


@api.get("/studio/history")
async def studio_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.studio_outputs.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(20)
    items = []
    async for c in cursor:
        items.append({
            "id": c["id"],
            "template": c["template"],
            "brief": c.get("brief", ""),
            "content": c["content"],
            "created_at": c["created_at"].isoformat() if isinstance(c.get("created_at"), datetime) else c.get("created_at"),
        })
    return {"items": items}


# ---------- Pilot ----------
@api.post("/pilot/plan")
async def pilot_plan(payload: PilotRequestIn,
                     current_user: Dict[str, Any] = Depends(get_current_user)):
    bp = current_user.get("business_profile") or {}
    lang = payload.language

    target_label_fr = {
        "restaurants": "restaurants",
        "importers": "importateurs",
        "distributors": "distributeurs",
        "wine_shops": "cavistes",
        "other": "autre",
    }.get(payload.target_type, payload.target_type)
    target_label_en = payload.target_type

    prompt_fr = f"""Entreprise : {bp.get('business_name') or '—'} | Produits : {bp.get('main_products') or 'vins/spiritueux'}
Cible : {target_label_fr}
Région cible : {payload.region}
Focus produit : {payload.product_focus or 'gamme principale'}

Génère un plan de prospection en JSON UNIQUEMENT (sans markdown), structure :
{{
  "summary": "résumé en 2 phrases de l'approche",
  "targets": [
    {{"name": "nom (suggestion à valider)", "city": "ville", "type": "{target_label_fr}", "approach": "angle d'approche en 1 phrase"}}
  ],
  "tasks": [
    {{"title": "tâche concrète", "deadline": "ex: cette semaine"}}
  ]
}}

Donne 5 cibles et 4 tâches. Les noms doivent être plausibles pour la région mais signalés comme suggestions."""
    prompt_en = f"""Business: {bp.get('business_name') or '—'} | Products: {bp.get('main_products') or 'wines/spirits'}
Target type: {target_label_en}
Target region: {payload.region}
Product focus: {payload.product_focus or 'main range'}

Generate a prospecting plan as JSON ONLY (no markdown), structure:
{{
  "summary": "2-sentence summary of the approach",
  "targets": [
    {{"name": "name (suggestion to validate)", "city": "city", "type": "{target_label_en}", "approach": "1-sentence approach angle"}}
  ],
  "tasks": [
    {{"title": "concrete task", "deadline": "e.g. this week"}}
  ]
}}

Provide 5 targets and 4 tasks. Names should be plausible for the region but flagged as suggestions."""

    chat = _make_chat(
        session_id=f"pilot_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_pilot_system(lang),
    )
    raw = await chat.send_message(UserMessage(text=prompt_fr if lang == "fr" else prompt_en))

    import json, re
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        plan = json.loads(cleaned)
    except Exception:
        plan = {
            "summary": raw[:200],
            "targets": [],
            "tasks": [],
        }

    doc_id = f"pilot_{uuid.uuid4().hex[:12]}"
    await db.pilot_plans.insert_one({
        "id": doc_id,
        "user_id": current_user["user_id"],
        "target_type": payload.target_type,
        "region": payload.region,
        "product_focus": payload.product_focus,
        "language": lang,
        "plan": plan,
        "created_at": _now(),
    })
    return {"id": doc_id, "plan": plan}


@api.get("/pilot/history")
async def pilot_history(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.pilot_plans.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(20)
    items = []
    async for c in cursor:
        items.append({
            "id": c["id"],
            "target_type": c["target_type"],
            "region": c["region"],
            "plan": c["plan"],
            "created_at": c["created_at"].isoformat() if isinstance(c.get("created_at"), datetime) else c.get("created_at"),
        })
    return {"items": items}




# ---------- Credits ----------
class CreditsOut(BaseModel):
    credits: int
    credit_price_eur: float
    action_cost: int


@api.get("/credits/me", response_model=CreditsOut)
async def credits_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return CreditsOut(
        credits=int(current_user.get("credits", 0)),
        credit_price_eur=CREDIT_PRICE_EUR,
        action_cost=ACTION_COST,
    )


async def _consume_credits(user_id: str, amount: int) -> int:
    """Atomically deduct credits. Triggers auto-recharge if enabled and balance drops
    below the configured threshold. Raises 402 if insufficient."""
    result = await db.users.find_one_and_update(
        {"user_id": user_id, "credits": {"$gte": amount}},
        {"$inc": {"credits": -amount}},
        return_document=True,
        projection={"_id": 0, "credits": 1, "auto_recharge": 1, "stripe_customer_id": 1, "stripe_payment_method_id": 1},
    )
    if not result:
        # Try emergency auto-recharge before failing
        topped = await _try_auto_recharge(user_id)
        if topped:
            return await _consume_credits(user_id, amount)
        raise HTTPException(
            status_code=402,
            detail="Crédits insuffisants. Rechargez votre compte pour continuer.",
        )
    # Schedule (non-blocking) auto-recharge if balance dropped below threshold
    ar = result.get("auto_recharge") or {}
    if ar.get("enabled") and result["credits"] <= int(ar.get("threshold") or 20) \
            and result.get("stripe_customer_id") and result.get("stripe_payment_method_id"):
        import asyncio as _asyncio
        _asyncio.create_task(_try_auto_recharge(user_id))
    return int(result["credits"])


async def _try_auto_recharge(user_id: str) -> bool:
    """Best-effort off-session Stripe charge using the stored card. Returns True on success."""
    if not STRIPE_SECRET_KEY:
        return False
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return False
    ar = user.get("auto_recharge") or {}
    if not ar.get("enabled"):
        return False
    if not (user.get("stripe_customer_id") and user.get("stripe_payment_method_id")):
        return False
    pack = PACK_BY_ID.get(ar.get("pack_id") or "starter")
    if not pack:
        return False
    try:
        intent = stripe.PaymentIntent.create(
            amount=int(round(pack["price_eur"] * 100)),
            currency="eur",
            customer=user["stripe_customer_id"],
            payment_method=user["stripe_payment_method_id"],
            off_session=True,
            confirm=True,
            description=f"EtOH auto-recharge — {pack['credits']} crédits",
            metadata={"user_id": user_id, "pack_id": pack["id"], "credits": str(pack["credits"]), "kind": "auto_recharge"},
        )
        if intent.status == "succeeded":
            await db.users.update_one({"user_id": user_id}, {"$inc": {"credits": pack["credits"]}})
            await db.wallet_checkouts.insert_one({
                "session_id": intent.id, "user_id": user_id, "pack_id": pack["id"],
                "credits": pack["credits"], "amount_eur": pack["price_eur"],
                "status": "paid", "kind": "auto_recharge", "paid_at": _now(), "created_at": _now(),
            })
            logger.info("Auto-recharge ok for %s: +%d credits", user_id, pack["credits"])
            return True
    except stripe.error.CardError as e:
        logger.warning("Auto-recharge declined for %s: %s", user_id, e.user_message or str(e))
    except Exception as e:
        logger.warning("Auto-recharge failed for %s: %s", user_id, e)
    return False


async def _log_action(user_id: str, action: str, payload: Dict[str, Any], cost: int):
    await db.action_log.insert_one({
        "id": f"act_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "action": action,
        "cost": cost,
        "payload": payload,
        "created_at": _now(),
    })


# ---------- Pilot v2: search + draft + send ----------
class PilotSearchIn(BaseModel):
    query: str  # e.g. "cavistes paris vins nature"
    language: Literal["fr", "en"] = "fr"


class PilotDraftIn(BaseModel):
    search_id: str
    target_id: str
    channel: Literal["email", "whatsapp", "linkedin"]
    custom_note: Optional[str] = None
    language: Literal["fr", "en"] = "fr"


class PilotSendEmailIn(BaseModel):
    target_id: str
    search_id: str
    to_email: EmailStr
    to_name: str
    subject: str
    body: str


class PilotOpenChannelIn(BaseModel):
    target_id: str
    search_id: str
    channel: Literal["whatsapp", "linkedin"]


@api.post("/pilot/search")
async def pilot_search(payload: PilotSearchIn,
                       current_user: Dict[str, Any] = Depends(llm_rate_limit(20))):
    """AI-driven contact suggestion. Free (no credit cost) — only outbound actions cost credits.

    NOTE: This is an AI-generated list of plausible contacts. Names, emails,
    phones and LinkedIn URLs are SUGGESTIONS to be validated by the user.
    """
    bp = current_user.get("business_profile") or {}
    lang = payload.language

    prompt_fr = f"""Tu es EtOH Pilot. L'utilisateur cherche des contacts commerciaux pour vendre ses {bp.get('main_products') or 'vins/spiritueux'}.
Profil utilisateur : {bp.get('business_name') or '—'} | Région : {bp.get('region') or '—'}.

Requête : "{payload.query}"

Génère 8 contacts plausibles correspondant à la requête, sous forme de JSON STRICT (sans markdown, sans ```).
Structure :
{{
  "interpretation": "Tu cherches X à Y, je vais cibler Z (1 phrase)",
  "targets": [
    {{
      "id": "t1",
      "name": "Nom de l'établissement",
      "type": "caviste|restaurant|importateur|distributeur|autre",
      "city": "Ville",
      "country": "Pays",
      "snippet": "1 ligne décrivant pourquoi c'est une bonne cible",
      "contact_name": "Prénom Nom du décideur (suggestion à valider)",
      "contact_role": "Acheteur, Sommelier, etc.",
      "email": "email plausible (suggestion à valider)",
      "phone": "+33 X XX XX XX XX (suggestion à valider)",
      "linkedin_url": "https://linkedin.com/in/... (si plausible)",
      "tags": ["bio", "naturel", "premium"]
    }}
  ]
}}
Marque CLAIREMENT toutes les coordonnées comme à valider — ne pas inventer de vrais comptes existants. 8 contacts exactement, variés en quartiers/types."""

    prompt_en = f"""You are EtOH Pilot. The user is looking for commercial contacts to sell their {bp.get('main_products') or 'wines/spirits'}.
User profile: {bp.get('business_name') or '—'} | Region: {bp.get('region') or '—'}.

Query: "{payload.query}"

Generate 8 plausible contacts matching the query as STRICT JSON (no markdown, no ```).
Structure:
{{
  "interpretation": "You're looking for X in Y, I'll target Z (1 sentence)",
  "targets": [
    {{
      "id": "t1",
      "name": "Business name",
      "type": "wine_shop|restaurant|importer|distributor|other",
      "city": "City",
      "country": "Country",
      "snippet": "1-line reason why it's a good target",
      "contact_name": "First Last (to validate)",
      "contact_role": "Buyer, Sommelier, etc.",
      "email": "plausible email (to validate)",
      "phone": "+XX XXX (to validate)",
      "linkedin_url": "https://linkedin.com/in/... (if plausible)",
      "tags": ["organic", "natural", "premium"]
    }}
  ]
}}
Mark ALL contact info as "to validate" — do not invent real existing accounts. Exactly 8 contacts, varied by neighborhood/type."""

    chat = _make_chat(
        session_id=f"pilot_search_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_pilot_system(lang),
    )
    raw = await chat.send_message(UserMessage(text=prompt_fr if lang == "fr" else prompt_en))

    import json, re
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        targets = parsed.get("targets", [])
        interpretation = parsed.get("interpretation", "")
    except Exception:
        targets = []
        interpretation = ""

    # Ensure stable ids and sanitise AI-generated email/phone/linkedin fields
    # (the model sometimes appends "(suggestion à valider)" inline which breaks
    # EmailStr validation downstream).
    import re as _re

    def _strip_parens(value: Optional[str]) -> Optional[str]:
        if not value or not isinstance(value, str):
            return value
        # Remove any trailing parenthetical comment + extra whitespace
        cleaned = _re.sub(r"\s*\([^)]*\)\s*$", "", value).strip()
        return cleaned

    for i, t in enumerate(targets):
        t["id"] = f"t{i+1}"
        t["email"] = _strip_parens(t.get("email"))
        t["phone"] = _strip_parens(t.get("phone"))
        t["linkedin_url"] = _strip_parens(t.get("linkedin_url"))
        t["contact_name"] = _strip_parens(t.get("contact_name"))

    search_id = f"sch_{uuid.uuid4().hex[:12]}"
    await db.pilot_searches.insert_one({
        "id": search_id,
        "user_id": current_user["user_id"],
        "query": payload.query,
        "language": lang,
        "interpretation": interpretation,
        "targets": targets,
        "created_at": _now(),
    })
    return {
        "search_id": search_id,
        "query": payload.query,
        "interpretation": interpretation,
        "targets": targets,
    }


@api.get("/pilot/searches")
async def pilot_searches(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.pilot_searches.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(20)
    items = []
    async for c in cursor:
        items.append({
            "id": c["id"],
            "query": c["query"],
            "target_count": len(c.get("targets", [])),
            "created_at": c["created_at"].isoformat() if isinstance(c.get("created_at"), datetime) else c.get("created_at"),
        })
    return {"items": items}


@api.post("/pilot/draft")
async def pilot_draft(payload: PilotDraftIn,
                      current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate AI-drafted message for a specific target + channel. FREE (cost only on send)."""
    search = await db.pilot_searches.find_one(
        {"id": payload.search_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")
    target = next((t for t in search.get("targets", []) if t.get("id") == payload.target_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    bp = current_user.get("business_profile") or {}
    lang = payload.language

    if payload.channel == "email":
        channel_instr_fr = "Format email : ligne 'Objet :' puis corps. 140-200 mots. Ton chaleureux et professionnel."
        channel_instr_en = "Email format: 'Subject:' line then body. 140-200 words. Warm professional tone."
    elif payload.channel == "whatsapp":
        channel_instr_fr = "Format WhatsApp : 60-100 mots max, direct, friendly mais pro. Pas d'objet, pas de signature longue. 1 emoji max."
        channel_instr_en = "WhatsApp format: 60-100 words max, direct, friendly but professional. No subject, short signature. 1 emoji max."
    else:  # linkedin
        channel_instr_fr = "Format message LinkedIn : 80-150 mots, ton pro et personnalisé. Pas d'objet."
        channel_instr_en = "LinkedIn message format: 80-150 words, professional and personalized tone. No subject line."

    prompt_fr = f"""Rédige un message de prospection commerciale pour ce contact.

CONTACT :
- Établissement : {target.get('name')} ({target.get('type')}, {target.get('city')})
- Décideur : {target.get('contact_name') or 'contact principal'} ({target.get('contact_role') or '—'})
- Pourquoi c'est une bonne cible : {target.get('snippet') or ''}
- Tags : {', '.join(target.get('tags') or [])}

PRODUCTEUR (EXPÉDITEUR) :
- {bp.get('business_name') or 'EtOH'} ({bp.get('region') or '—'})
- Produits : {bp.get('main_products') or 'vins/spiritueux'}
- Rôle de l'expéditeur : {bp.get('role') or 'Dirigeant'}

NOTE PERSO (à intégrer si fournie) : {payload.custom_note or '(aucune)'}

CANAL : {payload.channel.upper()}
{channel_instr_fr}

Réponds UNIQUEMENT avec le message rédigé, sans préambule."""

    prompt_en = f"""Write a commercial prospecting message for this contact.

CONTACT:
- Business: {target.get('name')} ({target.get('type')}, {target.get('city')})
- Decision-maker: {target.get('contact_name') or 'main contact'} ({target.get('contact_role') or '—'})
- Why it's a good target: {target.get('snippet') or ''}
- Tags: {', '.join(target.get('tags') or [])}

PRODUCER (SENDER):
- {bp.get('business_name') or 'EtOH'} ({bp.get('region') or '—'})
- Products: {bp.get('main_products') or 'wines/spirits'}
- Sender role: {bp.get('role') or 'Owner'}

CUSTOM NOTE (integrate if provided): {payload.custom_note or '(none)'}

CHANNEL: {payload.channel.upper()}
{channel_instr_en}

Reply ONLY with the message, no preamble."""

    chat = _make_chat(
        session_id=f"pilot_draft_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_studio_system(lang) + _brand_voice_block(bp, lang),
    )
    content = await chat.send_message(UserMessage(text=prompt_fr if lang == "fr" else prompt_en))

    # For email, try to split out subject
    subject = None
    body = content.strip()
    if payload.channel == "email":
        # Try to extract "Objet:" / "Subject:" first line
        first_line, _, rest = body.partition("\n")
        if first_line.lower().startswith(("objet", "subject")):
            _, _, subj_val = first_line.partition(":")
            subject = subj_val.strip().strip("*").strip()
            body = rest.lstrip()
    return {
        "target_id": payload.target_id,
        "channel": payload.channel,
        "subject": subject,
        "body": body,
    }


@api.post("/pilot/send-email")
async def pilot_send_email(payload: PilotSendEmailIn,
                           current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Sends an outbound email via Resend.
    *** MOCKED *** until RESEND_API_KEY is set + DNS validated on pilot.etoh.fr.
    Deducts 1 credit per send.
    """
    remaining = await _consume_credits(current_user["user_id"], ACTION_COST)

    # Auto-upsert into CRM (US-034)
    search = await db.pilot_searches.find_one(
        {"id": payload.search_id, "user_id": current_user["user_id"]}, {"_id": 0, "targets": 1}
    )
    if search:
        target = next((t for t in (search.get("targets") or []) if t.get("id") == payload.target_id), None)
        if target:
            await _upsert_crm_contact(current_user["user_id"], target, "email")

    real_send_attempted = False
    delivery_ok = True
    delivery_info: Dict[str, Any] = {"mocked": True}

    if RESEND_API_KEY:
        real_send_attempted = True
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
                        "to": [payload.to_email],
                        "subject": payload.subject,
                        "text": payload.body,
                        "reply_to": current_user["email"],
                    },
                )
            delivery_ok = r.status_code in (200, 202)
            delivery_info = {"mocked": False, "provider": "resend", "status": r.status_code, "body": r.text[:300]}
        except Exception as e:
            delivery_ok = False
            delivery_info = {"mocked": False, "provider": "resend", "error": str(e)[:300]}

    await _log_action(
        current_user["user_id"],
        "send_email",
        {
            "search_id": payload.search_id,
            "target_id": payload.target_id,
            "to_email": payload.to_email,
            "to_name": payload.to_name,
            "subject": payload.subject,
            "delivery": delivery_info,
        },
        cost=ACTION_COST,
    )

    return {
        "ok": delivery_ok,
        "mocked": not real_send_attempted,
        "credits_remaining": remaining,
        "delivery": delivery_info,
    }


@api.post("/pilot/open-channel")
async def pilot_open_channel(payload: PilotOpenChannelIn,
                             current_user: Dict[str, Any] = Depends(get_current_user)):
    """Record an outbound WhatsApp/LinkedIn action and deduct credits.
    The frontend opens the actual URL — we just track + charge."""
    remaining = await _consume_credits(current_user["user_id"], ACTION_COST)
    # Auto-upsert into CRM
    search = await db.pilot_searches.find_one(
        {"id": payload.search_id, "user_id": current_user["user_id"]}, {"_id": 0, "targets": 1}
    )
    if search:
        target = next((t for t in (search.get("targets") or []) if t.get("id") == payload.target_id), None)
        if target:
            await _upsert_crm_contact(current_user["user_id"], target, payload.channel)
    await _log_action(
        current_user["user_id"],
        f"open_{payload.channel}",
        {
            "search_id": payload.search_id,
            "target_id": payload.target_id,
            "channel": payload.channel,
        },
        cost=ACTION_COST,
    )
    return {"ok": True, "credits_remaining": remaining}


@api.get("/pilot/actions")
async def pilot_actions(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.action_log.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50)
    items = []
    async for c in cursor:
        items.append({
            "id": c["id"],
            "action": c["action"],
            "cost": c["cost"],
            "payload": c.get("payload", {}),
            "created_at": c["created_at"].isoformat() if isinstance(c.get("created_at"), datetime) else c.get("created_at"),
        })
    return {"items": items}


# ---------- Dashboard metrics (EtOH Score™ + KPIs + Level) ----------
@api.get("/dashboard/metrics")
async def dashboard_metrics(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Aggregated business activity → EtOH Score™, weekly KPIs, level, sprint progress."""
    uid = current_user["user_id"]
    now = _now()
    week_ago = now - timedelta(days=7)

    # --- Aggregates from action_log + pilot_searches ---
    week_actions_pipeline = [
        {"$match": {"user_id": uid, "created_at": {"$gte": week_ago}}},
        {"$group": {"_id": "$action", "count": {"$sum": 1}}},
    ]
    week_action_counts: Dict[str, int] = {}
    async for doc in db.action_log.aggregate(week_actions_pipeline):
        week_action_counts[doc["_id"]] = doc["count"]

    emails_sent = week_action_counts.get("send_email", 0)
    whatsapp_sent = week_action_counts.get("open_whatsapp", 0)
    linkedin_sent = week_action_counts.get("open_linkedin", 0)
    campaigns_sent = emails_sent + whatsapp_sent + linkedin_sent

    # Lifetime totals (for the Level)
    total_actions = await db.action_log.count_documents({"user_id": uid})
    total_searches = await db.pilot_searches.count_documents({"user_id": uid})
    total_studio = await db.studio_outputs.count_documents({"user_id": uid}) if hasattr(db, "studio_outputs") else 0
    try:
        total_studio = await db.studio_outputs.count_documents({"user_id": uid})
    except Exception:
        total_studio = 0
    try:
        total_coach = await db.coach_conversations.count_documents({"user_id": uid})
    except Exception:
        total_coach = 0

    # Targets identified this week (from this-week's searches)
    week_targets = 0
    distinct_regions = set()
    cursor = db.pilot_searches.find(
        {"user_id": uid, "created_at": {"$gte": week_ago}}, {"_id": 0, "targets": 1, "query": 1}
    )
    async for s in cursor:
        week_targets += len(s.get("targets", []))
        # crude region detection: take last word of query
        q = (s.get("query") or "").strip()
        if q:
            distinct_regions.add(q.lower().split()[-1])

    # Distributors contacted this week (target_type in payload — best effort)
    distributors_contacted = 0
    async for a in db.action_log.find(
        {"user_id": uid, "created_at": {"$gte": week_ago},
         "action": {"$in": ["send_email", "open_whatsapp", "open_linkedin"]}},
        {"_id": 0, "payload": 1}
    ):
        # we don't always know target.type at log time; rough proxy: count all as "distributors" if no info
        distributors_contacted += 1
    # The above duplicates campaigns_sent; refine: treat distributors_contacted as outbound to distinct targets
    distributors_contacted = min(distributors_contacted, campaigns_sent)

    # --- Weekly targets (goals — customizable per user, defaults from etoh.io) ---
    bp = current_user.get("business_profile") or {}
    GOAL_PROSPECTS = int(bp.get("goal_prospects") or 50)
    GOAL_CAMPAIGNS = int(bp.get("goal_campaigns") or 5)
    GOAL_DISTRIBUTORS = int(bp.get("goal_distributors") or 20)
    GOAL_MARKETS = int(bp.get("goal_markets") or 4)

    # --- EtOH Score™ — composite, capped at 100 ---
    def _pct(n, d):
        return min(100, int(round(100 * n / d))) if d > 0 else 0

    score_components = {
        "prospects": _pct(week_targets, GOAL_PROSPECTS),         # max 100
        "campaigns": _pct(campaigns_sent, GOAL_CAMPAIGNS),
        "distributors": _pct(distributors_contacted, GOAL_DISTRIBUTORS),
        "markets": min(100, int(round(100 * len(distinct_regions) / max(1, GOAL_MARKETS)))),
    }
    etoh_score = int(round(sum(score_components.values()) / len(score_components)))

    # --- Level (lifetime points) ---
    # 1 point per action (search/draft/send/coach msg/studio gen)
    lifetime_points = total_actions + total_searches + total_studio + total_coach
    if lifetime_points >= 1000:
        level = {"name": "International Brand", "icon": "💎", "min": 1000, "next": None, "progress_pct": 100}
    elif lifetime_points >= 500:
        level = {"name": "Exporter", "icon": "🥇", "min": 500, "next": 1000,
                 "progress_pct": int(round(100 * (lifetime_points - 500) / 500))}
    elif lifetime_points >= 100:
        level = {"name": "Grower", "icon": "🥈", "min": 100, "next": 500,
                 "progress_pct": int(round(100 * (lifetime_points - 100) / 400))}
    else:
        level = {"name": "Explorer", "icon": "🥉", "min": 0, "next": 100,
                 "progress_pct": int(round(100 * lifetime_points / 100)) if lifetime_points else 0}

    # --- Weekly Sprint (static template + live progress) ---
    sprint = [
        {"id": "prospects", "title": "Identifier 10 prospects qualifiés",
         "current": min(week_targets, 10), "target": 10, "done": week_targets >= 10},
        {"id": "email", "title": "Envoyer 1 campagne email",
         "current": min(emails_sent, 1), "target": 1, "done": emails_sent >= 1},
        {"id": "social", "title": "Publier 2 contenus (Studio)",
         "current": min(total_studio, 2), "target": 2, "done": total_studio >= 2},
        {"id": "crm", "title": "Contacter 5 nouveaux contacts",
         "current": min(campaigns_sent, 5), "target": 5, "done": campaigns_sent >= 5},
    ]
    done_count = sum(1 for s in sprint if s["done"])
    sprint_pct = int(round(100 * done_count / len(sprint)))

    return {
        "etoh_score": etoh_score,
        "score_components": score_components,
        "kpis": {
            "prospects_identified": {"current": week_targets, "target": GOAL_PROSPECTS},
            "campaigns_sent": {"current": campaigns_sent, "target": GOAL_CAMPAIGNS},
            "distributors_contacted": {"current": distributors_contacted, "target": GOAL_DISTRIBUTORS},
            "markets_analyzed": {"current": len(distinct_regions), "target": GOAL_MARKETS},
            "opportunities_detected": {"current": week_targets, "target": None},
        },
        "level": {**level, "lifetime_points": lifetime_points},
        "sprint": {"items": sprint, "progress_pct": sprint_pct},
    }

# ---------------------------------------------------------------------------
# Mount router & middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await db.user_sessions.create_index("user_id")
    await db.user_sessions.create_index("expires_at", expireAfterSeconds=0)
    # Stripe webhook idempotency
    await db.stripe_events.create_index("event_id", unique=True)
    await db.stripe_events.create_index("received_at", expireAfterSeconds=60 * 60 * 24 * 90)  # 90d TTL
    # Subscription invoice idempotency (separate from events — invoices have their own id)
    # _id is already unique in Mongo, no extra index needed.
    logger.info("EtOH backend started — indexes ensured.")


# ---------- US-003 — Profil Commercial synthétique ----------
@api.post("/profile/synthesize")
async def profile_synthesize(current_user: Dict[str, Any] = Depends(llm_rate_limit(10))):
    """Génère par IA un profil commercial synthétique (ICP / Positionnement / Priorités)
    à partir des données collectées lors de l'onboarding."""
    bp = current_user.get("business_profile") or {}
    lang = bp.get("language") or "fr"

    if lang == "fr":
        prompt = f"""Tu es expert en stratégie commerciale vins/bières/spiritueux.
Voici les données utilisateur :
- Type d'activité : {bp.get('business_type') or '—'}
- Nom : {bp.get('business_name') or '—'}
- Région : {bp.get('region') or '—'}
- Produits : {bp.get('main_products') or '—'}
- CA : {bp.get('revenue') or '—'}
- Prix moyen bouteille : {bp.get('avg_bottle_price') or '—'} €
- Prix moyen carton : {bp.get('avg_case_price') or '—'} €
- Pays cibles : {', '.join(bp.get('target_countries') or []) or '—'}
- Canaux : {', '.join(bp.get('target_channels') or []) or '—'}
- Objectifs : {', '.join(bp.get('objectives') or []) or '—'}

Renvoie UNIQUEMENT un JSON strict (pas de markdown, pas de ```) :
{{
  "positioning": "1 phrase courte décrivant le positionnement",
  "icp": [
    {{"label": "Type d'acheteur 1", "why": "1 phrase"}},
    {{"label": "Type d'acheteur 2", "why": "1 phrase"}},
    {{"label": "Type d'acheteur 3", "why": "1 phrase"}}
  ],
  "priorities": [
    "Priorité commerciale 1 — court terme",
    "Priorité commerciale 2 — moyen terme",
    "Priorité commerciale 3 — long terme"
  ],
  "tagline": "1 phrase d'accroche commerciale max 12 mots"
}}"""
    else:
        prompt = f"""You are a commercial strategy expert for wine/beer/spirits.
User data:
- Activity: {bp.get('business_type') or '—'}
- Name: {bp.get('business_name') or '—'}
- Region: {bp.get('region') or '—'}
- Products: {bp.get('main_products') or '—'}
- Revenue: {bp.get('revenue') or '—'}
- Avg bottle price: {bp.get('avg_bottle_price') or '—'} €
- Avg case price: {bp.get('avg_case_price') or '—'} €
- Target countries: {', '.join(bp.get('target_countries') or []) or '—'}
- Channels: {', '.join(bp.get('target_channels') or []) or '—'}
- Objectives: {', '.join(bp.get('objectives') or []) or '—'}

Return ONLY strict JSON (no markdown, no ```):
{{"positioning": "...", "icp": [{{"label":"...","why":"..."}},...], "priorities": ["...","...","..."], "tagline":"..."}}"""

    chat = _make_chat(
        session_id=f"synth_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_coach_system(lang),
    )
    raw = await chat.send_message(UserMessage(text=prompt))
    import json, re
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        synthesis = json.loads(cleaned)
    except Exception:
        synthesis = {"positioning": raw[:200], "icp": [], "priorities": [], "tagline": ""}

    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"business_profile.synthesis": synthesis, "business_profile.synthesis_at": _now()}},
    )
    return {"synthesis": synthesis}


# ---------- Auto-extract business info from free-form user messages ----------
class AutoExtractIn(BaseModel):
    message: str = Field(..., min_length=2, max_length=4000)
    source: Optional[str] = "chat"  # coach | studio | pilot | chat


_EXTRACT_FIELDS = [
    "business_name",
    "business_type",
    "region",
    "role",
    "main_products",
    "revenue",
    "avg_bottle_price",
    "avg_case_price",
    "objectives",
    "products",
    "target_countries",
    "target_channels",
]

_EXTRACT_ENUMS = {
    "business_type": [
        "winery", "cooperative", "merchant", "importer", "distributor",
        "restaurant", "brewery", "distillery", "wine_shop", "other",
    ],
    "revenue": ["<100k", "100k-500k", "500k-2M", "2M-10M", "10M+"],
    "objectives": [
        "distributors", "export", "clients", "visibility", "content", "time",
    ],
    "products": [
        "red_wine", "white_wine", "rose", "sparkling", "spirits",
        "beer", "alcohol_free", "other",
    ],
    "target_channels": [
        "CHR", "Cavistes", "GMS", "E-commerce", "Export",
        "Vente directe", "Marketplaces",
    ],
}


@api.post("/profile/auto-extract")
async def profile_auto_extract(
    payload: AutoExtractIn,
    current_user: Dict[str, Any] = Depends(llm_rate_limit(40)),
):
    """Claude-Cowork-style passive memory.

    Looks at the user's free-form chat message and extracts any new business
    profile info (business name, region, products, revenue, objectives…),
    then merges it into business_profile *without overwriting* fields already
    filled by the user. Returns the list of fields that were just learned.
    """
    bp = current_user.get("business_profile") or {}

    # Build a list of *missing* fields so we don't bother the LLM with the rest
    def is_empty(k: str) -> bool:
        v = bp.get(k)
        if v is None:
            return True
        if isinstance(v, (list, str)) and len(v) == 0:
            return True
        return False

    missing = [f for f in _EXTRACT_FIELDS if is_empty(f)]
    if not missing:
        return {"updated": {}, "learned_fields": []}

    enum_lines = []
    for f in missing:
        if f in _EXTRACT_ENUMS:
            enum_lines.append(f"- {f}: one of {_EXTRACT_ENUMS[f]}")
        elif f in ("objectives", "products", "target_countries", "target_channels"):
            enum_lines.append(f"- {f}: array of strings")
        else:
            enum_lines.append(f"- {f}: string")

    extract_prompt = (
        "You are a strict information extractor for a wine/spirits commercial app. "
        "Read the user's message and extract ONLY explicit factual info about THEIR business. "
        "Never invent. Never guess. If the message is generic / not about their business, "
        "return an empty JSON object.\n\n"
        "IMPORTANT for country names: ALWAYS use the French spelling "
        "(France, Belgique, Allemagne, Royaume-Uni, USA, Canada, Suisse, Japon, Chine, Italie, Espagne, Pays-Bas, Suède, Norvège, Danemark…).\n\n"
        "Fields to consider (only include those clearly stated in the message):\n"
        + "\n".join(enum_lines)
        + "\n\nReturn STRICT JSON only (no markdown, no ``` fences). "
        "Keys must match the field names above. Omit fields that are not stated.\n\n"
        + f'User message:\n"""{payload.message.strip()}"""'
    )

    chat = _make_chat(
        session_id=f"extract_{current_user['user_id']}_{uuid.uuid4().hex[:6]}",
        system_message=(
            "You output ONLY valid JSON. No prose, no markdown. "
            "If nothing relevant, output {}."
        ),
    )
    try:
        raw = await chat.send_message(UserMessage(text=extract_prompt))
    except Exception as e:
        logging.warning(f"auto-extract LLM failure: {e}")
        return {"updated": {}, "learned_fields": []}

    import json
    import re
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned) if cleaned else {}
    except Exception:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    # Sanitize: only accept fields that are (a) in our allowlist AND (b) still empty
    updates: Dict[str, Any] = {}
    for f in missing:
        if f not in parsed:
            continue
        val = parsed[f]
        if val is None:
            continue
        # type / enum validation
        if f in _EXTRACT_ENUMS and isinstance(_EXTRACT_ENUMS[f], list):
            allowed = _EXTRACT_ENUMS[f]
            if f in ("objectives", "products", "target_channels"):
                if not isinstance(val, list):
                    continue
                val = [v for v in val if v in allowed]
                if not val:
                    continue
            else:
                if val not in allowed:
                    continue
        if f in ("target_countries",):
            if not isinstance(val, list):
                continue
            val = [str(v).strip() for v in val if str(v).strip()]
            if not val:
                continue
        if isinstance(val, str):
            val = val.strip()
            if not val:
                continue
        updates[f] = val

    if not updates:
        return {"updated": {}, "learned_fields": []}

    mongo_set = {f"business_profile.{k}": v for k, v in updates.items()}
    mongo_set["business_profile.last_auto_learn_at"] = _now()
    mongo_set["business_profile.last_auto_learn_fields"] = list(updates.keys())
    mongo_set["business_profile.last_auto_learn_source"] = payload.source
    await db.users.update_one(
        {"user_id": current_user["user_id"]}, {"$set": mongo_set}
    )
    return {"updated": updates, "learned_fields": list(updates.keys())}


# ---------- Hub — Business Hub (universal portfolio) ----------
import re as _re_slug


def _slugify(text: str) -> str:
    if not text:
        return ""
    s = text.strip().lower()
    s = _re_slug.sub(r"[àáâãäå]", "a", s)
    s = _re_slug.sub(r"[èéêë]", "e", s)
    s = _re_slug.sub(r"[ìíîï]", "i", s)
    s = _re_slug.sub(r"[òóôõö]", "o", s)
    s = _re_slug.sub(r"[ùúûü]", "u", s)
    s = _re_slug.sub(r"[ç]", "c", s)
    s = _re_slug.sub(r"[ñ]", "n", s)
    s = _re_slug.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:48] or "hub"


async def _ensure_hub_slug(current_user: Dict[str, Any]) -> str:
    """Make sure the user has a stable, unique public slug for their Hub."""
    existing = (current_user.get("business_profile") or {}).get("hub_slug")
    if existing:
        return existing
    base = _slugify(
        (current_user.get("business_profile") or {}).get("business_name")
        or current_user.get("name")
        or current_user.get("email", "").split("@")[0]
        or "hub"
    )
    candidate = base
    n = 1
    while True:
        clash = await db.users.find_one(
            {"business_profile.hub_slug": candidate, "user_id": {"$ne": current_user["user_id"]}},
            {"user_id": 1},
        )
        if not clash:
            break
        n += 1
        candidate = f"{base}-{n}"
    await db.users.update_one(
        {"user_id": current_user["user_id"]},
        {"$set": {"business_profile.hub_slug": candidate}},
    )
    return candidate


HUB_ITEM_TYPES = {"product", "service", "document"}


class HubItemIn(BaseModel):
    type: str = Field(..., pattern="^(product|service|document)$")
    name: str = Field(..., min_length=1, max_length=180)
    category: Optional[str] = Field(None, max_length=80)
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field("EUR", max_length=8)
    description: Optional[str] = Field(None, max_length=4000)
    image_url: Optional[str] = Field(None, max_length=800)
    doc_url: Optional[str] = Field(None, max_length=800)
    tags: Optional[List[str]] = None
    available_markets: Optional[List[str]] = None
    sort_order: Optional[int] = 0
    featured: Optional[bool] = False


class HubItemPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=180)
    category: Optional[str] = Field(None, max_length=80)
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=8)
    description: Optional[str] = Field(None, max_length=4000)
    image_url: Optional[str] = Field(None, max_length=800)
    doc_url: Optional[str] = Field(None, max_length=800)
    tags: Optional[List[str]] = None
    available_markets: Optional[List[str]] = None
    sort_order: Optional[int] = None
    featured: Optional[bool] = None


def _strip_item(it: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in it.items() if k != "_id"}
    return out


@api.get("/hub/me")
async def hub_get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    slug = await _ensure_hub_slug(current_user)
    bp = current_user.get("business_profile") or {}
    items_cursor = db.hub_items.find({"user_id": current_user["user_id"]}).sort(
        [("sort_order", 1), ("created_at", 1)]
    )
    items = [_strip_item(it) async for it in items_cursor]
    return {
        "slug": slug,
        "company": {
            "name": bp.get("business_name") or current_user.get("name"),
            "business_type": bp.get("business_type"),
            "region": bp.get("region"),
            "role": bp.get("role"),
            "main_products": bp.get("main_products"),
            "language": bp.get("language") or "fr",
            "target_countries": bp.get("target_countries") or [],
            "target_channels": bp.get("target_channels") or [],
            "synthesis": bp.get("synthesis"),
        },
        "items": items,
    }


@api.post("/hub/items")
async def hub_create_item(
    payload: HubItemIn,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    if payload.type not in HUB_ITEM_TYPES:
        raise HTTPException(status_code=400, detail="invalid type")
    now = _now()
    item = {
        "id": f"hub_{uuid.uuid4().hex[:10]}",
        "user_id": current_user["user_id"],
        "type": payload.type,
        "name": payload.name.strip(),
        "category": (payload.category or "").strip() or None,
        "price": payload.price,
        "currency": (payload.currency or "EUR").upper(),
        "description": (payload.description or "").strip() or None,
        "image_url": payload.image_url,
        "doc_url": payload.doc_url,
        "tags": payload.tags or [],
        "available_markets": payload.available_markets or [],
        "sort_order": payload.sort_order or 0,
        "featured": bool(payload.featured),
        "created_at": now,
        "updated_at": now,
    }
    await db.hub_items.insert_one(item)
    return _strip_item(item)


@api.patch("/hub/items/{item_id}")
async def hub_update_item(
    item_id: str,
    payload: HubItemPatch,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    update = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="nothing to update")
    update["updated_at"] = _now()
    res = await db.hub_items.update_one(
        {"id": item_id, "user_id": current_user["user_id"]}, {"$set": update}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    it = await db.hub_items.find_one({"id": item_id})
    return _strip_item(it)


@api.delete("/hub/items/{item_id}")
async def hub_delete_item(
    item_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    res = await db.hub_items.delete_one({"id": item_id, "user_id": current_user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@api.get("/public/hub/{slug}")
async def public_hub(slug: str):
    user = await db.users.find_one({"business_profile.hub_slug": slug})
    if not user:
        raise HTTPException(status_code=404, detail="hub not found")
    bp = user.get("business_profile") or {}
    items_cursor = db.hub_items.find({"user_id": user["user_id"]}).sort(
        [("sort_order", 1), ("created_at", 1)]
    )
    items = [_strip_item(it) async for it in items_cursor]
    # Track an aggregated view counter (per-hub, not per-item).
    try:
        await db.hub_views.update_one(
            {"slug": slug},
            {"$inc": {"views": 1}, "$set": {"last_view_at": _now()}},
            upsert=True,
        )
    except Exception:
        pass
    owner_features = get_features(user)
    return {
        "slug": slug,
        "company": {
            "name": bp.get("business_name") or user.get("name") or "EtOH Hub",
            "business_type": bp.get("business_type"),
            "region": bp.get("region"),
            "main_products": bp.get("main_products"),
            "language": bp.get("language") or "fr",
            "target_countries": bp.get("target_countries") or [],
            "synthesis_tagline": ((bp.get("synthesis") or {}) or {}).get("tagline"),
            "synthesis_positioning": ((bp.get("synthesis") or {}) or {}).get("positioning"),
        },
        "items": items,
        # Public chat is only available for paying plans (Pro+).
        "chat_enabled": bool(owner_features["features"].get("hub_chat_public")),
    }


# ---------------------------------------------------------------------------
# Hub Phase 2 — Public conversational AI chat + lead capture
# ---------------------------------------------------------------------------
class PublicHubChatIn(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=2000)
    visitor_lang: Optional[str] = None  # auto-detected by Hub host or set by visitor


def _hub_chat_system_prompt(owner: Dict[str, Any], items: list, lang: str = "fr") -> str:
    bp = owner.get("business_profile") or {}
    name = bp.get("business_name") or owner.get("name") or "Domaine"
    products = [it for it in items if it.get("type") == "product"]
    services = [it for it in items if it.get("type") == "service"]
    countries = bp.get("target_countries") or []
    region = bp.get("region") or ""
    bt = bp.get("business_type") or ""
    synth = (bp.get("synthesis") or {})
    product_lines = [
        f"- {p['name']}"
        + (f" ({p.get('category')})" if p.get("category") else "")
        + (f" — {p.get('price')}€" if p.get("price") else "")
        + (f". {p.get('description')[:200]}" if p.get("description") else "")
        for p in products[:40]
    ]
    service_lines = [
        f"- {s['name']}" + (f" — {s.get('description', '')[:160]}" if s.get("description") else "")
        for s in services[:20]
    ]
    return f"""You are the official AI assistant of "{name}", a wine & spirits {bt}.

LANGUAGE: ALWAYS reply in {lang}. If the visitor switches language, follow them.

ABOUT THE BUSINESS:
- Name: {name}
- Region: {region or 'n/a'}
- Markets: {', '.join(countries) if countries else 'n/a'}
- Tagline: {synth.get('tagline') or 'n/a'}
- Positioning: {synth.get('positioning') or 'n/a'}

PRODUCTS ({len(products)}):
{chr(10).join(product_lines) if product_lines else '(none yet)'}

SERVICES ({len(services)}):
{chr(10).join(service_lines) if service_lines else '(none yet)'}

RULES:
1. Answer ONLY based on the info above. If asked about prices not listed, say you don't have that info and offer to put the visitor in touch with the team.
2. NEVER invent products, vintages, awards, or distributor info. If unsure, ask the visitor for clarification.
3. NEVER reveal wholesale pricing, internal margins, or confidential business data.
4. Be warm, expert, conversational. Use 1-3 short paragraphs max.
5. After 2-3 substantive exchanges, NATURALLY propose to take their name + email so the team can follow up with a brochure or quote. Example: "Pour vous envoyer notre brochure complète, puis-je avoir votre prénom et email ?".
6. Format: Plain text, no markdown headings (#), but you may use **bold** and bullet lists.
"""


@api.post("/public/hub/{slug}/chat")
@limiter.limit("10/minute")
async def public_hub_chat(request: Request, slug: str, payload: PublicHubChatIn):
    """Anonymous conversational chat for a public Hub. Rate-limited per IP."""
    owner = await db.users.find_one({"business_profile.hub_slug": slug})
    if not owner:
        raise HTTPException(404, "hub not found")
    feats = get_features(owner)
    if not feats["features"].get("hub_chat_public"):
        raise HTTPException(402, "public chat requires a paid plan on the hub owner side")

    # Items for context
    items_cursor = db.hub_items.find({"user_id": owner["user_id"]}).sort([("sort_order", 1)])
    items = [_strip_item(it) async for it in items_cursor]

    lang = (payload.visitor_lang or (owner.get("business_profile") or {}).get("language") or "fr").lower()
    if lang not in ("fr", "en", "pt", "es"):
        lang = "fr"

    # Get or create session
    sid = payload.session_id or f"hubchat_{uuid.uuid4().hex[:14]}"
    session = await db.hub_chat_sessions.find_one({"session_id": sid})
    history: list = list((session or {}).get("messages") or [])

    history.append({"role": "user", "content": payload.message, "ts": _now()})

    system_prompt = _hub_chat_system_prompt(owner, items, lang=lang)
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"hub_{slug}_{sid}",
        system_message=system_prompt,
    ).with_model("openai", "gpt-4o-mini")

    # Compact recent history (last 8 turns) for context
    recent_user_msgs = [m["content"] for m in history if m["role"] == "user"][-8:]
    blended = "\n\nPREVIOUS VISITOR MESSAGES:\n" + "\n".join(f"- {m}" for m in recent_user_msgs[:-1]) if len(recent_user_msgs) > 1 else ""
    try:
        reply = await chat.send_message(UserMessage(text=payload.message + blended))
    except Exception as e:
        logger.warning("hub chat LLM failure: %s", e)
        raise HTTPException(503, "AI assistant temporarily unavailable")

    history.append({"role": "assistant", "content": reply, "ts": _now()})

    # Persist session (truncate to last 40 messages)
    history = history[-40:]
    client_ip = request.client.host if request.client else None
    await db.hub_chat_sessions.update_one(
        {"session_id": sid},
        {
            "$set": {
                "session_id": sid,
                "slug": slug,
                "hub_owner_id": owner["user_id"],
                "messages": history,
                "language": lang,
                "last_message_at": _now(),
                "ip": client_ip,
            },
            "$setOnInsert": {"created_at": _now(), "lead_captured": False},
        },
        upsert=True,
    )

    return {
        "session_id": sid,
        "reply": reply,
        "language": lang,
        "user_message_count": sum(1 for m in history if m["role"] == "user"),
    }


class HubLeadIn(BaseModel):
    session_id: str
    name: Optional[str] = Field(default=None, max_length=200)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=40)
    company: Optional[str] = Field(default=None, max_length=200)
    consent: bool = True


@api.post("/public/hub/{slug}/lead")
@limiter.limit("5/minute")
async def public_hub_lead(request: Request, slug: str, payload: HubLeadIn):
    """Capture a lead from a public Hub visitor and create a prospect in the owner's CRM."""
    owner = await db.users.find_one({"business_profile.hub_slug": slug})
    if not owner:
        raise HTTPException(404, "hub not found")
    if not payload.consent:
        raise HTTPException(400, "consent required (RGPD)")

    sess = await db.hub_chat_sessions.find_one({"session_id": payload.session_id, "slug": slug})
    transcript_excerpt = ""
    if sess:
        msgs = (sess.get("messages") or [])[-10:]
        transcript_excerpt = "\n".join(
            f"{m['role'].upper()}: {m.get('content', '')[:300]}"
            for m in msgs
            if isinstance(m, dict)
        )

    # Create prospect for the hub owner
    prospect_id = f"pr_{uuid.uuid4().hex[:12]}"
    await db.prospects.insert_one({
        "id": prospect_id,
        "user_id": owner["user_id"],
        "name": payload.name or (payload.email.split("@")[0]),
        "email": str(payload.email),
        "phone": payload.phone,
        "company": payload.company,
        "source": "hub_public_chat",
        "hub_slug": slug,
        "tags": ["hub-lead"],
        "notes": f"Lead via Hub public chat ({slug}). Session {payload.session_id}.\n\nTranscript:\n{transcript_excerpt[:2000]}",
        "status": "new",
        "created_at": _now(),
        "updated_at": _now(),
    })

    # Update session
    if sess:
        await db.hub_chat_sessions.update_one(
            {"session_id": payload.session_id},
            {"$set": {
                "lead_captured": True,
                "lead_email": str(payload.email),
                "lead_name": payload.name,
                "lead_captured_at": _now(),
                "prospect_id": prospect_id,
            }},
        )

    # Fire-and-forget Resend email to the hub owner (best-effort)
    try:
        if RESEND_API_KEY:
            import requests as _rq
            bp = owner.get("business_profile") or {}
            hub_name = bp.get("business_name") or owner.get("name") or "votre Hub"
            html = f"""<h2>🎉 Nouveau lead via {hub_name}</h2>
<p><b>Nom:</b> {payload.name or '—'}<br>
<b>Email:</b> {payload.email}<br>
<b>Téléphone:</b> {payload.phone or '—'}<br>
<b>Entreprise:</b> {payload.company or '—'}</p>
<p>Le contact est désormais visible dans votre CRM Pilot (source: hub_public_chat).</p>
<p style="font-size:12px;color:#888">Conversation:</p>
<pre style="background:#f5f5f5;padding:12px;border-radius:6px;font-size:11px">{transcript_excerpt[:3000]}</pre>"""
            _rq.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
                    "to": [owner.get("email")],
                    "subject": f"🆕 Nouveau lead via {hub_name}",
                    "html": html,
                },
                timeout=8,
            )
    except Exception as e:
        logger.warning("hub lead email send failed: %s", e)

    return {"ok": True, "prospect_id": prospect_id}


# ---------------------------------------------------------------------------
# Phase D — Enrichment endpoint (OpenFoodFacts EAN lookup, for the Hub products)
# ---------------------------------------------------------------------------
@api.get("/enrich/ean/{ean}")
async def enrich_by_ean(ean: str, user=Depends(get_current_user)):
    """Lookup a product by EAN/barcode via the free Open Food Facts API.

    Works well for spirits and most retail wines. Returns a normalised dict the
    frontend can use to auto-fill a Hub product form.
    """
    ean = "".join(c for c in ean if c.isdigit())
    if len(ean) < 8 or len(ean) > 14:
        raise HTTPException(400, "EAN must be 8-14 digits")
    import requests as _rq
    try:
        r = _rq.get(f"https://world.openfoodfacts.org/api/v2/product/{ean}.json", timeout=10)
    except Exception as e:
        raise HTTPException(503, f"OpenFoodFacts unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(404, "EAN not found")
    body = r.json() or {}
    if body.get("status") != 1 or not body.get("product"):
        raise HTTPException(404, "EAN not found")
    p = body["product"]
    return {
        "found": True,
        "ean": ean,
        "name": p.get("product_name") or p.get("product_name_fr") or p.get("product_name_en"),
        "brand": (p.get("brands") or "").split(",")[0].strip() or None,
        "category": (p.get("categories") or "").split(",")[-1].strip() or None,
        "ingredients": p.get("ingredients_text_fr") or p.get("ingredients_text"),
        "abv": p.get("alcohol_value"),  # may be present for spirits
        "country": (p.get("countries") or "").split(",")[0].strip() or None,
        "image_url": p.get("image_front_url") or p.get("image_url"),
        "raw_url": f"https://world.openfoodfacts.org/product/{ean}",
    }


# ---------- Hub IA extraction (URL scrape / free text → products & services) ----------
class HubExtractIn(BaseModel):
    source_type: str = Field(..., pattern="^(url|text)$")
    source: str = Field(..., min_length=2, max_length=200_000)


async def _fetch_url_text(url: str) -> str:
    """Best-effort web scraper: returns plain text from URL (truncated to ~20k chars)."""
    import requests
    from bs4 import BeautifulSoup

    if not url.startswith("http"):
        url = "https://" + url
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_0) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "fr,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de charger l'URL : {e}")
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Compact multiple newlines
    text = "\n".join([ln.strip() for ln in text.splitlines() if ln.strip()])
    return text[:20_000]


@api.post("/hub/extract")
async def hub_extract(
    payload: HubExtractIn,
    current_user: Dict[str, Any] = Depends(llm_rate_limit(10)),
):
    """Ingest a URL or free text and create draft products/services via the LLM."""
    bp = current_user.get("business_profile") or {}
    lang = bp.get("language") or "fr"

    if payload.source_type == "url":
        material = await _fetch_url_text(payload.source.strip())
    else:
        material = payload.source.strip()

    if len(material) < 30:
        raise HTTPException(status_code=400, detail="Contenu trop court pour extraire quoi que ce soit.")

    extract_prompt = (
        "You are an EXTRACTOR for a wine/spirits/drinks B2B app. Read the supplied source "
        "(website text or free description) and identify the COMPANY's commercial offering. "
        "Output STRICT JSON with the following shape (no markdown, no fences, no commentary):\n\n"
        "{\n"
        '  "company": {\n'
        '    "name": str | null,\n'
        '    "business_type": "winery|cooperative|merchant|importer|distributor|restaurant|brewery|distillery|wine_shop|other" | null,\n'
        '    "region": str | null,\n'
        '    "positioning": str | null,\n'
        '    "tagline": str | null\n'
        "  },\n"
        '  "products": [ {\n'
        '    "name": str (required),\n'
        '    "category": str | null,\n'
        '    "price": number | null,\n'
        '    "currency": "EUR" | "USD" | "GBP" | null,\n'
        '    "description": str (1-3 sentences, factual),\n'
        '    "tags": [str]\n'
        "  } ],\n"
        '  "services": [ {\n'
        '    "name": str (required),\n'
        '    "category": str | null,\n'
        '    "description": str (1-3 sentences),\n'
        '    "tags": [str]\n'
        "  } ]\n"
        "}\n\n"
        "RULES:\n"
        "- Never invent — if a price is not stated, use null.\n"
        "- Limit to at most 20 products and 10 services.\n"
        "- Trim duplicates (same name).\n"
        "- Skip generic site sections (legal, blog, careers, login, cookies).\n"
        f"- Write descriptions in {('French' if lang == 'fr' else 'English' if lang == 'en' else 'Portuguese' if lang == 'pt' else 'Spanish')}.\n\n"
        f"SOURCE:\n\"\"\"{material}\"\"\""
    )

    chat = _make_chat(
        session_id=f"hub_extract_{current_user['user_id']}_{uuid.uuid4().hex[:6]}",
        system_message="You output ONLY valid JSON. No prose, no markdown, no code fences.",
    )
    try:
        raw = await chat.send_message(UserMessage(text=extract_prompt))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    import json
    import re
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned) if cleaned else {}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM returned invalid JSON: {e}")

    company = parsed.get("company") or {}
    products = parsed.get("products") or []
    services = parsed.get("services") or []
    if not isinstance(products, list):
        products = []
    if not isinstance(services, list):
        services = []

    # Update business_profile (only empty fields, never overwrite)
    company_updates: Dict[str, Any] = {}
    if isinstance(company.get("name"), str) and not bp.get("business_name"):
        company_updates["business_profile.business_name"] = company["name"].strip()[:120]
    if isinstance(company.get("region"), str) and not bp.get("region"):
        company_updates["business_profile.region"] = company["region"].strip()[:120]
    if isinstance(company.get("business_type"), str) and not bp.get("business_type"):
        if company["business_type"] in {
            "winery", "cooperative", "merchant", "importer", "distributor",
            "restaurant", "brewery", "distillery", "wine_shop", "other",
        }:
            company_updates["business_profile.business_type"] = company["business_type"]
    # Soft "synthesis" enrichment if missing
    syn = bp.get("synthesis") or {}
    if isinstance(company.get("tagline"), str) and not syn.get("tagline"):
        syn["tagline"] = company["tagline"].strip()[:200]
        company_updates["business_profile.synthesis"] = syn
    if isinstance(company.get("positioning"), str) and not syn.get("positioning"):
        syn["positioning"] = company["positioning"].strip()[:500]
        company_updates["business_profile.synthesis"] = syn
    if company_updates:
        await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": company_updates})

    # Insert items
    now = _now()
    created_items: List[Dict[str, Any]] = []

    def _norm_currency(c: Any) -> str:
        if not isinstance(c, str):
            return "EUR"
        cu = c.strip().upper()
        return cu if cu in {"EUR", "USD", "GBP", "CHF", "CAD"} else "EUR"

    for idx, p in enumerate(products[:20]):
        name = p.get("name") if isinstance(p, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        price = p.get("price")
        if not isinstance(price, (int, float)):
            price = None
        item = {
            "id": f"hub_{uuid.uuid4().hex[:10]}",
            "user_id": current_user["user_id"],
            "type": "product",
            "name": name.strip()[:180],
            "category": (str(p.get("category")).strip()[:80] if p.get("category") else None),
            "price": float(price) if price is not None else None,
            "currency": _norm_currency(p.get("currency")),
            "description": (str(p.get("description")).strip()[:4000] if p.get("description") else None),
            "image_url": None,
            "doc_url": None,
            "tags": [str(t)[:40] for t in (p.get("tags") or []) if t][:8],
            "available_markets": [],
            "sort_order": idx,
            "featured": False,
            "created_at": now,
            "updated_at": now,
        }
        await db.hub_items.insert_one(item)
        created_items.append(_strip_item(item))

    for idx, sv in enumerate(services[:10]):
        name = sv.get("name") if isinstance(sv, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        item = {
            "id": f"hub_{uuid.uuid4().hex[:10]}",
            "user_id": current_user["user_id"],
            "type": "service",
            "name": name.strip()[:180],
            "category": (str(sv.get("category")).strip()[:80] if sv.get("category") else None),
            "price": None,
            "currency": "EUR",
            "description": (str(sv.get("description")).strip()[:4000] if sv.get("description") else None),
            "image_url": None,
            "doc_url": None,
            "tags": [str(t)[:40] for t in (sv.get("tags") or []) if t][:8],
            "available_markets": [],
            "sort_order": idx,
            "featured": False,
            "created_at": now,
            "updated_at": now,
        }
        await db.hub_items.insert_one(item)
        created_items.append(_strip_item(item))

    return {
        "products_created": sum(1 for x in created_items if x["type"] == "product"),
        "services_created": sum(1 for x in created_items if x["type"] == "service"),
        "company_updated": bool(company_updates),
        "items": created_items,
    }


# ---------- US-034 — CRM léger ----------
class CrmContactStatus(str):
    new = "new"
    contacted = "contacted"
    replied = "replied"
    in_discussion = "in_discussion"
    won = "won"
    lost = "lost"


class CrmContactPatch(BaseModel):
    status: Optional[Literal["new", "contacted", "replied", "in_discussion", "won", "lost"]] = None
    notes: Optional[str] = None


async def _upsert_crm_contact(user_id: str, target: Dict[str, Any], channel: str):
    """Auto-create or upsert a CRM contact when user performs an outbound action."""
    key = f"crm_{user_id}_{target.get('name','')[:30]}_{target.get('city','')[:20]}".replace(" ", "_").lower()
    now = _now()
    existing = await db.crm_contacts.find_one({"key": key}, {"_id": 0})
    if existing:
        await db.crm_contacts.update_one(
            {"key": key},
            {"$set": {
                "last_contacted_at": now,
                "last_channel": channel,
                "status": "contacted" if existing.get("status") in (None, "new") else existing.get("status"),
            },
             "$inc": {"contact_count": 1}},
        )
    else:
        await db.crm_contacts.insert_one({
            "id": f"crm_{uuid.uuid4().hex[:12]}",
            "key": key,
            "user_id": user_id,
            "name": target.get("name"),
            "type": target.get("type"),
            "city": target.get("city"),
            "country": target.get("country"),
            "contact_name": target.get("contact_name"),
            "contact_role": target.get("contact_role"),
            "email": target.get("email"),
            "phone": target.get("phone"),
            "linkedin_url": target.get("linkedin_url"),
            "tags": target.get("tags") or [],
            "status": "contacted",
            "notes": "",
            "contact_count": 1,
            "first_contacted_at": now,
            "last_contacted_at": now,
            "last_channel": channel,
            "created_at": now,
        })


@api.get("/crm/contacts")
async def crm_list(current_user: Dict[str, Any] = Depends(get_current_user)):
    cursor = db.crm_contacts.find(
        {"user_id": current_user["user_id"]}, {"_id": 0, "key": 0}
    ).sort("last_contacted_at", -1).limit(200)
    items = []
    async for c in cursor:
        for k in ("first_contacted_at", "last_contacted_at", "created_at"):
            if isinstance(c.get(k), datetime):
                c[k] = c[k].isoformat()
        items.append(c)
    return {"items": items, "total": len(items)}


@api.patch("/crm/contacts/{contact_id}")
async def crm_update(contact_id: str, payload: CrmContactPatch,
                     current_user: Dict[str, Any] = Depends(get_current_user)):
    update = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = _now()
    r = await db.crm_contacts.update_one(
        {"id": contact_id, "user_id": current_user["user_id"]}, {"$set": update}
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}


@api.delete("/crm/contacts/{contact_id}")
async def crm_delete(contact_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    r = await db.crm_contacts.delete_one(
        {"id": contact_id, "user_id": current_user["user_id"]}
    )
    return {"deleted": r.deleted_count}


@api.get("/crm/export")
async def crm_export(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Returns CSV string of all CRM contacts (for download)."""
    cursor = db.crm_contacts.find(
        {"user_id": current_user["user_id"]}, {"_id": 0, "key": 0}
    ).sort("last_contacted_at", -1)
    import csv, io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Nom", "Type", "Ville", "Pays", "Contact", "Rôle", "Email", "Téléphone",
        "LinkedIn", "Statut", "Canal", "Tentatives", "Premier contact", "Dernier contact", "Notes",
    ])
    count = 0
    async for c in cursor:
        writer.writerow([
            c.get("name"), c.get("type"), c.get("city"), c.get("country"),
            c.get("contact_name"), c.get("contact_role"),
            c.get("email"), c.get("phone"), c.get("linkedin_url"),
            c.get("status"), c.get("last_channel"),
            c.get("contact_count"),
            (c.get("first_contacted_at").isoformat() if isinstance(c.get("first_contacted_at"), datetime) else c.get("first_contacted_at")) or "",
            (c.get("last_contacted_at").isoformat() if isinstance(c.get("last_contacted_at"), datetime) else c.get("last_contacted_at")) or "",
            c.get("notes") or "",
        ])
        count += 1
    return {"csv": buf.getvalue(), "count": count}


# ---------- US-022 — Coach veille concurrentielle (Tavily) ----------
async def _tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Calls Tavily web-search API. Returns a list of {title, url, content, score}."""
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": TAVILY_API_KEY,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": False,
                    "max_results": max_results,
                },
            )
        if r.status_code != 200:
            logger.warning("Tavily error: %s %s", r.status_code, r.text[:200])
            return []
        data = r.json()
        return data.get("results") or []
    except Exception as e:
        logger.warning("Tavily exception: %s", e)
        return []


class ResearchIn(BaseModel):
    query: str
    language: Literal["fr", "en"] = "fr"


@api.post("/coach/research")
async def coach_research(payload: ResearchIn,
                         current_user: Dict[str, Any] = Depends(llm_rate_limit(15))):
    """Search the web with Tavily, then have Coach synthesise the findings into actionable insights."""
    results = await _tavily_search(payload.query, max_results=6)
    sources_block = "\n".join(
        f"- {r.get('title')} ({r.get('url')}):\n  {(r.get('content') or '')[:400]}"
        for r in results
    )
    lang = payload.language
    bp = current_user.get("business_profile") or {}
    if lang == "fr":
        prompt = f"""Tu fais une veille marché pour le profil suivant : {bp.get('business_name') or '—'} ({bp.get('main_products') or 'vins/spiritueux'}).

Question : "{payload.query}"

Sources web (Tavily) :
{sources_block or '(aucune source — pas de clé Tavily ou résultat vide)'}

Synthétise en 3 blocs :
1. **Insights clés** (3 bullets max, factuels)
2. **Opportunités pour mon business** (2-3 bullets actionnables)
3. **Sources** (lien + 1 phrase)

Si pas de sources, indique clairement que la veille n'a pas pu être effectuée."""
    else:
        prompt = f"""Market intel for the following profile: {bp.get('business_name') or '—'} ({bp.get('main_products') or 'wines/spirits'}).

Question: "{payload.query}"

Web sources (Tavily):
{sources_block or '(no sources — missing key or empty result)'}

Synthesise in 3 blocks: Key insights, Opportunities for my business, Sources."""

    chat = _make_chat(
        session_id=f"research_{current_user['user_id']}_{uuid.uuid4().hex[:8]}",
        system_message=_coach_system(lang),
    )
    reply = await chat.send_message(UserMessage(text=prompt))
    return {
        "query": payload.query,
        "sources": [{"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("content") or "")[:200]} for r in results],
        "synthesis": reply,
        "tavily_enabled": bool(TAVILY_API_KEY),
    }


# ---------- US-050/051/052 — Stripe Wallet ----------
class CheckoutIn(BaseModel):
    pack_id: Literal["starter", "growth", "pro"]
    success_url: str
    cancel_url: str


@api.get("/wallet/packs")
async def wallet_packs(_: Dict[str, Any] = Depends(get_current_user)):
    return {"packs": CREDIT_PACKS, "currency": "eur", "credit_unit_eur": CREDIT_PRICE_EUR}


@api.post("/wallet/checkout")
async def wallet_checkout(payload: CheckoutIn,
                          current_user: Dict[str, Any] = Depends(get_current_user)):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured (missing STRIPE_SECRET_KEY).")
    pack = PACK_BY_ID.get(payload.pack_id)
    if not pack:
        raise HTTPException(status_code=400, detail="Unknown pack id")
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card", "sepa_debit"],
            customer_email=current_user["email"],
            customer_creation="always",
            payment_intent_data={"setup_future_usage": "off_session"},
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": int(round(pack["price_eur"] * 100)),
                    "product_data": {
                        "name": f"EtOH — {pack['credits']} crédits ({pack['label']})",
                        "description": f"Pack {pack['label']} · {pack['credits']} crédits @ {CREDIT_PRICE_EUR:.3f} €/crédit",
                    },
                },
                "quantity": 1,
            }],
            success_url=payload.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=payload.cancel_url,
            metadata={
                "user_id": current_user["user_id"],
                "pack_id": pack["id"],
                "credits": str(pack["credits"]),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    # Persist intent for later reconciliation
    await db.wallet_checkouts.insert_one({
        "session_id": session.id,
        "user_id": current_user["user_id"],
        "pack_id": pack["id"],
        "credits": pack["credits"],
        "amount_eur": pack["price_eur"],
        "status": "pending",
        "created_at": _now(),
    })
    return {"checkout_url": session.url, "session_id": session.id}


@api.get("/wallet/checkout/{session_id}")
async def wallet_checkout_status(session_id: str,
                                 current_user: Dict[str, Any] = Depends(get_current_user)):
    """Poll endpoint for the success page to confirm payment + credit the wallet."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    record = await db.wallet_checkouts.find_one(
        {"session_id": session_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not record:
        raise HTTPException(status_code=404, detail="Checkout not found")
    if record["status"] == "paid":
        return {"status": "paid", "credits_added": record["credits"]}
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")
    if session.payment_status == "paid":
        # Idempotent credit add
        result = await db.wallet_checkouts.update_one(
            {"session_id": session_id, "status": "pending"},
            {"$set": {"status": "paid", "paid_at": _now()}},
        )
        if result.modified_count > 0:
            user_set: Dict[str, Any] = {}
            if session.customer:
                user_set["stripe_customer_id"] = session.customer if isinstance(session.customer, str) else session.customer.id
            # Retrieve payment intent to grab the payment method id for off-session usage
            try:
                pi_id = session.payment_intent if isinstance(session.payment_intent, str) else (session.payment_intent and session.payment_intent.id)
                if pi_id:
                    pi = stripe.PaymentIntent.retrieve(pi_id)
                    if pi.payment_method:
                        user_set["stripe_payment_method_id"] = pi.payment_method if isinstance(pi.payment_method, str) else pi.payment_method.id
            except Exception as e:
                logger.warning("Could not retrieve PaymentIntent for off-session storage: %s", e)
            update: Dict[str, Any] = {"$inc": {"credits": record["credits"]}}
            if user_set:
                update["$set"] = user_set
            await db.users.update_one({"user_id": current_user["user_id"]}, update)
        return {"status": "paid", "credits_added": record["credits"]}
    return {"status": session.payment_status or "pending"}


@api.get("/wallet/usage")
async def wallet_usage(current_user: Dict[str, Any] = Depends(get_current_user)):
    """US-051 — usage breakdown by action over the last 30 days."""
    now = _now()
    since = now - timedelta(days=30)
    pipeline = [
        {"$match": {"user_id": current_user["user_id"], "created_at": {"$gte": since}}},
        {"$group": {"_id": "$action", "credits": {"$sum": "$cost"}, "count": {"$sum": 1}}},
    ]
    by_action: Dict[str, Dict[str, int]] = {}
    total = 0
    async for d in db.action_log.aggregate(pipeline):
        by_action[d["_id"]] = {"credits": d["credits"], "count": d["count"]}
        total += d["credits"]
    return {
        "period_days": 30,
        "total_credits_spent": total,
        "total_eur_spent": round(total * CREDIT_PRICE_EUR, 2),
        "by_action": by_action,
        "current_balance": int(current_user.get("credits", 0)),
    }


class AutoRechargeIn(BaseModel):
    enabled: bool
    threshold: Optional[int] = 20      # credits below which auto-recharge kicks in
    pack_id: Optional[Literal["starter", "growth", "pro"]] = "starter"


@api.put("/wallet/auto-recharge")
async def wallet_auto_recharge(payload: AutoRechargeIn,
                               current_user: Dict[str, Any] = Depends(get_current_user)):
    """US-052 — toggle auto-recharge preference (actual charging requires saved
    Stripe Customer + payment method; this endpoint stores the preference)."""
    update = {
        "auto_recharge.enabled": bool(payload.enabled),
        "auto_recharge.threshold": int(payload.threshold or 20),
        "auto_recharge.pack_id": payload.pack_id or "starter",
        "auto_recharge.updated_at": _now(),
    }
    await db.users.update_one({"user_id": current_user["user_id"]}, {"$set": update})
    return {"ok": True, "preference": {
        "enabled": payload.enabled,
        "threshold": payload.threshold,
        "pack_id": payload.pack_id,
    }}


app.include_router(api)


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
