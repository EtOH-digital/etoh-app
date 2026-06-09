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


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class BusinessProfileIn(BaseModel):
    business_name: Optional[str] = None
    business_type: Optional[Literal["winery", "cooperative", "merchant", "spirits", "other"]] = None
    region: Optional[str] = None
    main_products: Optional[str] = None
    role: Optional[str] = None
    language: Optional[Literal["fr", "en"]] = "fr"


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
        system_message=_studio_system(lang),
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


# ---------------------------------------------------------------------------
# Mount router & middleware
# ---------------------------------------------------------------------------
app.include_router(api)

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


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
