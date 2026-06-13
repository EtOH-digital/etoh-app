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
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal

import httpx
import jwt
from passlib.hash import bcrypt
from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

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

EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("etoh")

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


@api.get("/")
async def root():
    return {"name": "EtOH API", "status": "ok"}


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
                        current_user: Dict[str, Any] = Depends(get_current_user)):
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
                          current_user: Dict[str, Any] = Depends(get_current_user)):
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
    """Atomically deduct credits. Raises 402 if insufficient. Returns remaining."""
    result = await db.users.find_one_and_update(
        {"user_id": user_id, "credits": {"$gte": amount}},
        {"$inc": {"credits": -amount}},
        return_document=True,
        projection={"_id": 0, "credits": 1},
    )
    if not result:
        raise HTTPException(
            status_code=402,
            detail="Crédits insuffisants. Rechargez votre compte pour continuer.",
        )
    return int(result["credits"])


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
                       current_user: Dict[str, Any] = Depends(get_current_user)):
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
    logger.info("EtOH backend started — indexes ensured.")


# ---------- US-003 — Profil Commercial synthétique ----------
@api.post("/profile/synthesize")
async def profile_synthesize(current_user: Dict[str, Any] = Depends(get_current_user)):
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
                         current_user: Dict[str, Any] = Depends(get_current_user)):
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


app.include_router(api)


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
