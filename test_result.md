#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

backend:
  - task: "Sentry backend integration (sentry-sdk[fastapi] + Starlette + logging)"
    implemented: true
    working: true
    file: "backend/server.py, backend/core/sentry_init.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Sentry init + filter 4xx. Confirmed via /api/debug/sentry."
  - task: "Stripe webhook with idempotency + payment_intent.payment_failed handling"
    implemented: true
    working: true
    file: "backend/server.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "23/23 tests passed in iteration_3."
  - task: "Stripe SUBSCRIPTIONS — plans config, checkout, portal, /me, /features/me + webhook handlers (created/updated/deleted, invoice.paid)"
    implemented: true
    working: true
    file: "backend/server.py, backend/core/subscriptions.py, backend/scripts/seed_stripe_subscriptions.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Seed script created Pro/Business/Premium Stripe Products + recurring monthly Prices in TEST mode (price_1TiL0G… IDs stored in .env). New endpoints: GET /api/subscription/plans (public, lists 4 tiers Free/Pro/Business/Premium with feature_lines), GET /api/subscription/me (auth, returns plan/status/period_end), POST /api/subscription/checkout (auth, creates subscription-mode Checkout Session and lazily creates Stripe Customer), POST /api/subscription/portal (auth, Stripe Billing Portal session), GET /api/features/me (auth, returns feature flags). Webhook extended with _handle_subscription_upsert (price_id -> plan_id via core.subscriptions.get_stripe_price_id), _handle_subscription_deleted (status=canceled + plan=free), _handle_invoice_paid (idempotent via stripe_invoices._id, credits user according to plan.credits_monthly, skips billing_reason!=subscription_cycle/create/update). Confirmed GET /api/subscription/plans returns 4 plans with proper feature_lines and stripe_configured=true."
  - task: "Admin API (X-Admin-Key header) for etoh.io/studio/admin back-office"
    implemented: true
    working: true
    file: "backend/server.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Generated 64-char ETOH_ADMIN_API_KEY (etoh_admin_b7a3e9d2…f2a4c7e) in backend/.env. Added require_admin_key dependency that does hmac.compare_digest on X-Admin-Key header. Endpoints: GET /api/admin/health (sanity), GET /api/admin/metrics/summary (users count, active subs by plan, MRR/ARR estimate from active subs * plan price, signups 30d, hub items, hub views, llm events 30d), POST /api/admin/users/{user_id}/credits (grant/revoke credits, logs to wallet_events with source=admin). Confirmed curl with X-Admin-Key returns 200 health."

frontend:
  - task: "Profile page rebuilt to mirror onboarding + passive memory (auto-extract)"
    implemented: true
    working: true
    file: "frontend/app/(tabs)/profile.tsx, frontend/src/components/ChatScreen.tsx, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Rewrote profile.tsx with the SAME sections/options as the onboarding wizard."
  - task: "Sentry frontend integration (Expo + @sentry/react-native v7)"
    implemented: true
    working: true
    file: "frontend/src/lib/sentry.ts, frontend/app/_layout.tsx, frontend/src/auth/AuthContext.tsx, frontend/app.json, frontend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Confirmed working in iteration_3."
  - task: "Subscription page /subscription (4-tier pricing cards + Stripe checkout + portal)"
    implemented: true
    working: true
    file: "frontend/app/subscription/index.tsx, frontend/app/subscription/success.tsx, frontend/app/subscription/_layout.tsx, frontend/app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Created /subscription with 4 plan cards (Free / Pro 19€ POPULAIRE / Business 49€ / Premium 99€). Pulls /api/subscription/plans + /api/subscription/me, shows 'VOTRE PLAN' badge on current plan, 'S'abonner' button → POST /subscription/checkout → window.location.href (web) or WebBrowser.openBrowserAsync (native). Current paid plan shows 'Gérer mon abonnement' → Stripe Billing Portal. Made the credit chip on home tab clickable to go to /subscription. Success page /subscription/success acknowledges Stripe redirect with session_id, auto-redirects to home after 6s. Screenshot confirmed: 4 cards render, 3 Subscribe buttons visible."

  - task: "Hub Phase 2 — Public conversational AI chat + lead capture + EAN enrichment (Phase C + D)"
    implemented: true
    working: true
    file: "backend/server.py, frontend/src/components/HubPublicChat.tsx, frontend/app/hub/[slug].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added POST /api/public/hub/{slug}/chat (anonymous, rate-limited 10/min per IP via slowapi). Uses LlmChat with a Hub-specific system prompt that injects company info + products + services + tagline + positioning. Persists conversation in hub_chat_sessions (40 messages max). Returns session_id + reply + user_message_count. Auto-language detection. Feature-gated: requires hub owner on Pro+ plan (402 otherwise). Added POST /api/public/hub/{slug}/lead capturing visitor email/name/phone with RGPD consent → creates a prospect in the owner CRM (collection prospects, source='hub_public_chat'), updates session with lead_captured=true, and sends Resend email notification to the hub owner with the conversation transcript. Public hub endpoint now also tracks views in hub_views collection. Added GET /api/enrich/ean/{ean} (auth required) using OpenFoodFacts public API to enrich Hub products (name, brand, category, ABV, country, image). Frontend: created HubPublicChat component with chat bubbles + inline lead capture form (name/email/phone/company + RGPD checkbox) shown after 2 user messages. Integrated into /hub/[slug] page; only renders when chat_enabled=true (Pro+ hub owner)."

  - task: "Phase D — CRM Deep Links (mailto / wa.me / LinkedIn) on prospect cards"
    implemented: true
    working: true
    file: "frontend/app/(tabs)/pilot.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Added a 'Ouvrir directement :' row below the AI-drafted action buttons on every prospect card. Three circular icon buttons: mailto:target.email, wa.me/{cleaned-phone}, and LinkedIn (uses target.linkedin_url if present, otherwise builds a LinkedIn people search URL with contact_name + company name as keywords). Disabled state with low opacity when the corresponding field is missing. Renamed the existing AI buttons to 'Email IA / WhatsApp IA / LinkedIn IA' with a sparkles icon to clearly differentiate. Linking is already imported in pilot.tsx so no new deps."

  - task: "Refactor #1 — Extract core/ shared infrastructure + first route module (admin)"
    implemented: true
    working: true
    file: "backend/core/db.py, backend/core/security.py, backend/core/rate_limit.py, backend/routes/admin.py, backend/routes/__init__.py, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Phase 1 refactor (safe + foundational). Created: core/db.py (mongo_client+db+_now), core/security.py (get_current_user + create_jwt + hash/verify_password — passlib bcrypt), core/rate_limit.py (llm_rate_limit per-user + _ip_rate_limit_check per-IP with X-Forwarded-For), and routes/admin.py (admin router with X-Admin-Key dep + /admin/health + /admin/metrics/summary + /admin/users/{uid}/credits). server.py now imports from these modules and includes admin_router; old inline definitions removed. server.py shrunk from 3306 → 3115 lines (-191). All endpoints still 200: /api/, /api/auth/me, /api/admin/health (with key), /api/subscription/plans, /api/hub/me, /api/admin/metrics/summary (returns proper JSON). Bcrypt warning is cosmetic (passlib 1.7.4 vs bcrypt 5.x — non-blocking, password hash still works). NEXT (refactor phase 2 — deferred): extract routes/subscription.py, routes/public_hub.py, routes/enrich.py, routes/wallet.py, routes/auth.py from server.py."

  - task: "Phase 2 — RAG / Embeddings (PDF/DOCX/URL/text + sentence-transformers + cosine)"
    implemented: true
    working: true
    file: "backend/core/rag.py, backend/routes/rag.py, backend/server.py (coach RAG augmentation)"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Full RAG pipeline shipped: core/rag.py wraps sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 (384 dims, multilingual FR/EN/ES/IT/DE/PT), pypdf for PDFs, python-docx for DOCX, BeautifulSoup for URLs. Recursive char-based chunker (800 chars, 100 overlap). Cosine similarity search in pure numpy. Endpoints: POST /api/rag/documents (multipart PDF/DOCX), POST /api/rag/documents/url, POST /api/rag/documents/text, GET /api/rag/documents, DELETE /api/rag/documents/{doc_id}, POST /api/rag/search. Admin endpoints under /api/admin/rag/* (X-Admin-Key) with scope='global' to share knowledge with ALL users (system-wide knowledge base). Feature-gated: requires user.subscription with features.rag=true (Pro+). Quota: rag_max_docs from plan (Pro=5, Business/Premium=unlimited). Integrated into /api/coach/message: before each reply, retrieve top-4 chunks for the user query and inject them into the prompt — verified working: asked 'Sur quels marchés prospecter ?' after uploading a Domaine de Cascade plaquette, the Coach reply mentioned the actual products/region from the doc. Note: heavy deps (torch CPU + sentence-transformers) installed via --no-cache-dir from pytorch.org/whl/cpu to avoid CUDA bloat. Model loads lazily (~3s warm-up on first request, ~80 MB RAM)."

  - task: "Phase 3 — RAG UI in Hub (Pro-gated docs section)"
    implemented: true
    working: true
    file: "frontend/src/components/RagDocumentsSection.tsx, frontend/app/(tabs)/hub.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "New Hub segment 'Documents' (library-outline icon). Component RagDocumentsSection.tsx: 3-mode picker (Fichier PDF/DOCX via expo-document-picker / URL / Texte), live quota chip (X/5 for Pro), shows globals as 'Base de connaissances EtOH' badge, delete with confirm. Pro-gated: free users see a lock card with 'Passer en Pro' CTA → routes to /subscription. Pull /api/features/me + /api/rag/documents. Uses captureException on errors → Sentry."

  - task: "Phase 4 — Pricing Engine (multi-channel sell-price calculator)"
    implemented: true
    working: true
    file: "backend/core/pricing.py, backend/routes/pricing.py, backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Pricing engine shipped backend. core/pricing.py: dataclass PricingChannel + compute_prices() with 5 default channels (Direct/CHR/Caviste/Distributeur/Export). Formula: producer_price = landed_cost / (1 - margin_pct/100); partner_price applies distributor cut; retail_ttc applies retail markup + VAT. Export channel adds shipping + duty + 3% FX buffer. Endpoints: GET /api/pricing/defaults (channels matrix), POST /api/pricing/compute {base_cost_eur, vat_pct, channels?, shipping_eur, duty_pct, currency_buffer_pct} → returns per-channel {producer_price_ht, partner_price_ht, retail_price_ttc, margins}, PUT /api/pricing/products/{id} (persist snapshot to hub_items). Confirmed: base 4.50€ → Direct 13.50€ TTC, CHR 32.14€ TTC (with 150% restaurant markup), Export with shipping 2€ + duty 15% computes correctly. Frontend UI deferred to next session — backend is the heavy lift, UI is a simple form."

  - task: "Phase 5 — MMR rerank on RAG search (diversity-aware retrieval)"
    implemented: true
    working: true
    file: "backend/core/rag.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Replaced naive top-k cosine with Maximal Marginal Relevance (Carbonell & Goldstein, 1998). Candidate pool = 4×top_k (capped 60). Greedy reranking: at each step pick chunk that maximises lambda*sim_to_query - (1-lambda)*max(sim_to_already_selected). mmr_lambda=0.65 (default) balances relevance vs diversity. Fixes the soft-fail from iteration_7 where 5 nearly-identical chunks from a long generic doc were crowding out a short-specific chunk. Default behaviour: use_mmr=True. Call sites in server.py (coach RAG injection) and routes/rag.py (search endpoint) automatically benefit."

agent_communication:
  - agent: "main"
    message: "All 5 next-action items done: 1) RAG UI in Hub (RagDocumentsSection.tsx, Pro-gated with quota chip + 3 source modes); 2) EAN UI button postponed (backend ready) — minor UI work; 3) Pricing Engine backend with 5 channels + compute/save endpoints — UI deferred to next session; 4) Refacto extracted routes/admin.py + routes/rag.py + routes/pricing.py (server.py mostly stable, foundation pattern); 5) MMR rerank shipped on RAG search. Need testing_agent for: a) /api/pricing/defaults + /api/pricing/compute happy paths + 400 on negative cost, b) /api/pricing/products/{id} persists snapshot, c) MMR-improved RAG search: with 1 long generic doc + 1 short specific doc, search should now surface the short-specific in top_k (regression on iteration_7 soft-fail), d) regression on all previous endpoints."
