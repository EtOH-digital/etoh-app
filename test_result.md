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
        comment: "Rewrote profile.tsx with the SAME sections/options as the onboarding wizard: Métier tiles (10 options w/ emojis), CA radio rows, Objectifs check rows, Produits big chips, Prix/Pays/Canaux small chips. Added debounced (800ms) auto-save on every field change — top of the screen now shows a profile-completion progress bar + 'Enregistré automatiquement' indicator. Added a Claude-Cowork-style 'EtOH a appris automatiquement: …' banner that surfaces what was auto-learned. Implemented backend endpoint POST /api/profile/auto-extract that uses the LLM to extract business info from any chat message (only fills empty fields, never overwrites). Hooked into ChatScreen so every user message in Coach/Studio/Pilot fires the extractor fire-and-forget and shows a transient learning banner. Verified visually + via curl (returned learned_fields: ['target_countries'] from a French free-text message)."
  - task: "Unified ChatGPT-like UX across Coach / Studio / Pilot (true unification)"
    implemented: true
    working: true
    file: "frontend/app/(tabs)/coach.tsx, studio.tsx, pilot.tsx + frontend/src/components/ChatScreen.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Refactored into a single shared `ChatScreen` component used by all 3 modules. Same layout (logo header, empty state with title/subtitle, 4 suggestion chips, chat messages, input bar with send) — only the brand color, title, subtitle, suggestions, placeholder and onSend handler differ per module. Coach uses red, Studio uses navy, Pilot uses teal. Studio auto-detects template/tone from message keywords. Pilot keeps email/whatsapp/linkedin action modal but renders prospect cards as extras under the assistant bubble. Verified visually: each module loads, accepts ?prompt= pre-fill, sends a message, and renders the AI reply correctly."
  - task: "Unified Chat UX + Boost prompt pre-fill (Coach/Studio/Pilot)"
    implemented: true
    working: true
    file: "frontend/app/(tabs)/coach.tsx, studio.tsx, pilot.tsx, index.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Verified visually via screenshots. Dashboard 'Boost' on a recommendation routes to the correct module and pre-fills the input. Coach chat input pre-filled. Pilot search bar pre-filled. Studio brief pre-filled (template + tone selectors retained). Fixed missing `Fonts` import in studio.tsx that was breaking the screen."

agent_communication:
  - agent: "main"
    message: "Verified the unified UX & Boost prompt pre-filling across the three modules. Found and fixed a runtime error in studio.tsx (missing Fonts import). All three module screens now load and pre-fill from ?prompt= correctly."
