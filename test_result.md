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
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Wired Sentry into the Expo app. initSentry() runs at module load (before SplashScreen.preventAutoHideAsync), DSN from EXPO_PUBLIC_SENTRY_DSN. RootLayout exported via Sentry.wrap. AuthContext now calls setSentryUser on every setUser. Confirmed via browser console: '[Sentry] initialised {env: development}'. App still loads the language picker correctly."

backend:
  - task: "Sentry backend integration (sentry-sdk[fastapi] + Starlette + logging)"
    implemented: true
    working: true
    file: "backend/server.py, backend/core/sentry_init.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added core/sentry_init.py with FastApi+Starlette+Logging integrations. init_sentry() called BEFORE FastAPI() in server.py so the middleware kicks in. SENTRY_DSN read from .env. Filter drops 4xx HTTPException to keep noise low. Confirmed via /api/debug/sentry which raises a RuntimeError and the stderr shows 'Sentry is attempting to send 2 pending events'. Need a Sentry dashboard check to confirm event ingestion + verify user context is attached after login."
  - task: "Stripe webhook with idempotency + payment_intent.payment_failed handling"
    implemented: true
    working: true
    file: "backend/server.py, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Switched env to Stripe TEST keys (sk_test_, pk_test_, whsec_). Webhook now mounted at BOTH /api/wallet/webhook (legacy) and /api/stripe/webhook (canonical). Added Mongo collection stripe_events with unique index on event_id (created at startup) for proper idempotency. Handles checkout.session.completed (credits user + marks wallet_checkouts paid) and payment_intent.payment_failed (logs failure code/message). 90-day TTL on stripe_events. Signature verification active with the new whsec_ secret. Need to verify with stripe CLI replay or Dashboard 'Send test event'."

agent_communication:
  - agent: "main"
    message: "P0 progress: Stripe switched to TEST keys + proper webhook with idempotency. Sentry online both frontend and backend (verified locally). Ready for testing_agent to validate: 1) all auth/coach/studio/pilot/hub/crm/wallet endpoints still work after the Sentry middleware insertion, 2) the Stripe webhook accepts a properly-signed event (use a mock checkout.session.completed payload signed with whsec_QVCyl4ZUwgAqGrcVGT72D887khZoLFh5 — see test plan), 3) replay protection via stripe_events.event_id unique index, 4) /api/debug/sentry returns 500 (intentional)."
