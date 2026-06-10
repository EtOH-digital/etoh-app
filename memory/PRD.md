# EtOH — Product Requirements Document

## Vision
EtOH is an AI Commercial Director specialized in wines & spirits, designed for SME wine/spirit producers.
Three integrated AI modules answer the three fundamental questions every producer faces:
1. **Coach** (Red `#c7263e`) — "What should I do?" — AI business advisor
2. **Studio** (Navy `#1f3a5f`) — "How should I do it?" — AI content creator
3. **Pilot** (Teal `#4ba3b7`) — "Who should I do it with?" — AI prospecting executor

## Tech Stack
- **Frontend**: Expo SDK 54 (Expo Router, React Native), Web preview at `/`
- **Backend**: FastAPI (Python 3.11), all routes under `/api/*`
- **Database**: MongoDB (local cluster)
- **LLM**: OpenAI `gpt-4o-mini` via Emergent Universal Key (`emergentintegrations` lib)
- **Fonts**: Expletus Sans Bold (headings) + Lato (body), loaded via `@expo-google-fonts/*`
- **Auth**: JWT email/password + Emergent-managed Google OAuth
- **Outbound email**: Resend integration (currently **MOCKED** until customer provides API key + DNS for `pilot.etoh.fr` subdomain)

## Features

### Iteration 1 — MVP (delivered)
- ✅ Auth (signup, login, Google OAuth, `/auth/me`, logout)
- ✅ Bottom tab navigation: Home / Coach / Studio / Pilot / Profile
- ✅ Home: AI-generated Top 3 weekly actions tailored to user's business profile
- ✅ Coach: chat with persistent session, suggested prompts, multi-turn history
- ✅ Studio: 6 content templates (LinkedIn, email campaign, sales message, product description, trade show follow-up, presentation), tone selector, copy & share
- ✅ Pilot v1 (legacy): generic prospecting plan with target list + tasks
- ✅ Profile: business profile CRUD (name, type, region, products, role, FR/EN language)
- ✅ Bilingual FR/EN

### Iteration 2 — Pilot v2 + Credits + Brand identity (delivered)
- ✅ **Brand identity**: EtOH logo (color + white variants) for Studio (navy) and Pilot (teal). Coach uses red `#c7263e`.
- ✅ **Typography**: Expletus Sans Bold on headings, Lato on body text, applied across the app.
- ✅ **Credits system**: 100 free credits at signup. Each outbound action (email send / WhatsApp open / LinkedIn open) costs 1 credit. 1 credit = **0,099 €**. Credit badge visible on Home + Pilot. 402 Payment Required when exhausted.
- ✅ **Pilot v2 — semantic AI search**: free-form query like "cavistes paris vins nature" → AI proposes 8 plausible contacts with name, type, city, contact person, email, phone, LinkedIn URL, tags. All contact data is marked "(à valider)" and sanitised so it parses as valid emails for downstream sending.
- ✅ **Three outbound channels per target**:
  - **Email**: AI drafts subject + body, user edits, click "Envoyer" → Resend (mocked) sends + 1 credit deducted
  - **WhatsApp**: AI drafts message, opens `wa.me/{phone}?text=...` + 1 credit deducted
  - **LinkedIn**: AI drafts message, copies to clipboard + opens contact LinkedIn URL + 1 credit deducted
- ✅ **Action log** at `/api/pilot/actions` (history of every email/WhatsApp/LinkedIn action)

## API Endpoints

| Method | Path | Auth | Cost | Description |
|---|---|---|---|---|
| POST | `/api/auth/signup` | – | – | Create JWT account |
| POST | `/api/auth/login` | – | – | Login |
| POST | `/api/auth/google/session` | – | – | Exchange Emergent session_id → token |
| GET | `/api/auth/me` | Bearer | – | Current user |
| POST | `/api/auth/logout` | Bearer | – | Invalidate session |
| PUT | `/api/profile` | Bearer | – | Update business profile |
| GET | `/api/credits/me` | Bearer | – | Get current credit balance |
| POST | `/api/home/recommendations` | Bearer | – | 3 weekly AI actions |
| POST | `/api/coach/message` | Bearer | – | Coach chat |
| GET | `/api/coach/sessions` | Bearer | – | List Coach conversations |
| POST | `/api/studio/generate` | Bearer | – | Generate content |
| GET | `/api/studio/history` | Bearer | – | List past Studio outputs |
| **POST** | **`/api/pilot/search`** | Bearer | – | **AI contact search** (free) |
| GET | `/api/pilot/searches` | Bearer | – | Search history |
| **POST** | **`/api/pilot/draft`** | Bearer | – | **AI drafts msg for channel** (free) |
| **POST** | **`/api/pilot/send-email`** | Bearer | **1 credit** | **Send via Resend (MOCKED)** |
| **POST** | **`/api/pilot/open-channel`** | Bearer | **1 credit** | **Track WhatsApp/LinkedIn open** |
| GET | `/api/pilot/actions` | Bearer | – | Outbound action log |
| POST | `/api/pilot/plan` (legacy) | Bearer | – | Old plan endpoint, still works |

## Operational notes

### Resend activation (when ready)
1. Customer provides a `RESEND_API_KEY` in `/app/backend/.env`
2. Customer chooses a subdomain (recommended: `pilot.etoh.fr`) and sets `RESEND_FROM_EMAIL`
3. Customer adds the 4 DNS records on `etoh.fr` zone (SPF, DKIM, MX, DMARC) per Resend dashboard
4. Once `RESEND_API_KEY` is set, `/api/pilot/send-email` automatically switches from MOCKED to real send (no code change). Response will return `mocked: false`.

### Credit top-ups (Stripe integration TODO)
- Phase 2 will add Stripe Checkout for credit packs (e.g. 100 = 9,90€, 500 = 49,50€, 2000 = 198€)
- Until then, credits are managed via direct DB update (`db.users.update_one({...}, {"$set": {"credits": N}})`)

## Future Phases
- **Phase 2**: Stripe checkout for credit packs + Resend activation + Google Places API for real address data
- **Phase 3**: RAG — upload Word/Excel/PDF docs (global EtOH base + per-user private base), embeddings, citation in AI answers across Coach/Studio/Pilot

## MVP Success Metric
A wine producer signs up → 100 free credits → on Pilot, types "cavistes paris vins nature" → in <60s receives 8 actionable suggested contacts → drafts an email in 1 click → sends → 1 credit deducted. **The user feels: "I just made my first prospect contact, all I did was type one sentence."**
