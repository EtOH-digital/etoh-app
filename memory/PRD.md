# EtOH — Product Requirements Document

## Vision
EtOH is an AI Commercial Director specialized in wines & spirits. It helps producers (wineries, cooperatives, merchants, distillers) sell more by answering three fundamental questions through three integrated modules:
1. **What should I do?** → **Coach** (Red `#c7263e`) — AI business advisor
2. **How should I do it?** → **Studio** (Dark Blue `#1a365d`) — AI content creator
3. **Who should I do it with?** → **Pilot** (Light Blue `#4ba3b7`) — AI prospecting executor

## Target Users
- Wine producers, wineries, cooperatives, wine merchants, spirits producers
- SME owners, sales managers, export managers, marketing managers
- Non-technical, business-oriented

## Tech Stack
- **Frontend**: Expo SDK 54 (React Native) with Expo Router, runs on iOS, Android, and Web preview
- **Backend**: FastAPI (Python) with MongoDB
- **LLM**: Emergent Universal Key → OpenAI `gpt-4o-mini` (via `emergentintegrations`)
- **Auth**: JWT email/password + Emergent Google OAuth (shared user record by email)

## MVP Features (DELIVERED)
- ✅ Authentication: email/password signup + login, Google OAuth (Emergent managed)
- ✅ Bottom tab navigation: Home / Coach / Studio / Pilot / Profile
- ✅ **Home**: AI-generated Top 3 weekly action recommendations (refreshable, business-profile aware)
- ✅ **Coach**: chat interface with suggested prompts, multi-turn conversation, session persistence (MongoDB)
- ✅ **Studio**: 6 content templates (LinkedIn post, email campaign, sales message, product description, trade show follow-up, commercial presentation) with 4 tones, copy & share output
- ✅ **Pilot**: prospecting plan generator (restaurants / importers / distributors / wine shops) with target list + actionable tasks (checkbox completion)
- ✅ **Profile**: business profile CRUD (name, type, region, products, role, language FR/EN), logout
- ✅ Bilingual FR/EN (auto-applies to AI outputs based on user preference)

## Architecture
```
/app
├── backend/
│   ├── server.py          # FastAPI app, all /api/* routes
│   ├── .env               # MONGO_URL, EMERGENT_LLM_KEY, JWT_SECRET
│   └── requirements.txt
└── frontend/
    ├── app/               # expo-router routes
    │   ├── _layout.tsx    # root + AuthProvider
    │   ├── index.tsx      # redirect splash
    │   ├── (auth)/
    │   │   └── login.tsx
    │   └── (tabs)/
    │       ├── _layout.tsx
    │       ├── index.tsx  # Home
    │       ├── coach.tsx
    │       ├── studio.tsx
    │       ├── pilot.tsx
    │       └── profile.tsx
    └── src/
        ├── theme.ts       # color tokens
        ├── api/client.ts  # fetch wrapper + token storage
        └── auth/AuthContext.tsx
```

## API Endpoints
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/signup` | – | Create account (email + password) |
| POST | `/api/auth/login` | – | Email/password login |
| POST | `/api/auth/google/session` | – | Exchange Emergent session_id → user + token |
| GET | `/api/auth/me` | Bearer | Current user |
| POST | `/api/auth/logout` | Bearer | Invalidate session |
| PUT | `/api/profile` | Bearer | Update business profile |
| POST | `/api/home/recommendations` | Bearer | Get top 3 weekly AI actions |
| POST | `/api/coach/message` | Bearer | Send a message to AI Coach |
| GET | `/api/coach/sessions` | Bearer | List past conversations |
| GET | `/api/coach/sessions/{id}` | Bearer | Get conversation detail |
| POST | `/api/studio/generate` | Bearer | Generate content (template + brief) |
| GET | `/api/studio/history` | Bearer | List past Studio outputs |
| POST | `/api/pilot/plan` | Bearer | Generate prospecting plan |
| GET | `/api/pilot/history` | Bearer | List past Pilot plans |

## Success Metric (from brief)
A wine producer opens the app and within 3 minutes receives:
- one recommendation (Home)
- one piece of content (Studio)
- one commercial action to execute (Pilot)
→ User feels: **"I know exactly what I should do next to grow my sales."**

## Future Enhancements
- Streaming responses (SSE) on Coach for faster perceived latency
- Apple Sign-In (required by App Store if other social logins are present)
- Export Studio outputs to PDF/Word
- Pilot integration with CRM (HubSpot, Pipedrive) to auto-create deals
- Premium subscription (Stripe) — gating after X actions/month
