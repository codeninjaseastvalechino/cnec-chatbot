# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Project Is

An AI-powered automation agent for **Code Ninjas Eastvale Chino** that accepts
natural language instructions and executes scheduling, data retrieval, and
administrative tasks across three platforms.

**Long-term vision:** Package and sell to other Code Ninjas centers as a
multi-tenant SaaS product. Keep all code config-driven — no hardcoded
center-specific values anywhere.

Full requirements: `CNEC-Chatbot-Requirements.md`

---

## ⚠️ Python 3.9 Constraint (Critical)

**The user is on Python 3.9.** Do NOT use new type hint syntax:
- ❌ `str | None` → ✅ `Optional[str]`
- ❌ `list[X]` → ✅ `List[X]`
- ❌ `dict[str, X]` → ✅ `Dict[str, X]`

Always import from `typing`: `from typing import Optional, List, Dict, Any, Union, Tuple`

---

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| **Setup** | `pip install -r requirements.txt && playwright install chromium` | One-time only |
| **CLI (Milestone 1)** | `python3 run_milestone1.py` | Show/reschedule tours, real LineLeader data |
| **Web UI (mock)** | `TEST_MODE=true python3 app.py` | Zero API costs, instant feedback |
| **Web UI (real)** | `python3 app.py` | Uses Claude API + LineLeader data |
| **Chatbot CLI** | `python3 test_chatbot.py` | Debug chatbot engine without web UI |
| **Clear token** | `rm -f browser_state/lineleader_token.json` | Force fresh login |
| **View logs** | `tail -f logs/cnec_chatbot.log \| jq .` | Stream structured JSON logs |
| **Set provider** | `LLM_PROVIDER=ollama python3 app.py` | Switch to Ollama backend |

---

## Table of Contents

- [Current Status](#current-status)
- [Multi-Provider LLM Architecture](#multi-provider-llm-architecture)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables) ← NEW
- [How to Run](#how-to-run) ← REORGANIZED
- [Dependencies & Setup](#dependencies--setup) ← NEW
- [Development Commands](#development-commands)
- [Testing](#testing) ← CLARIFIED
- [Debugging & Troubleshooting](#debugging--troubleshooting)
- [Claude API Models & Pricing](#claude-api-models--pricing)
- [Safety & Design](#safety--design) ← NEW
- [Architecture Decision Log](#architecture-decision-log)
- [Open Questions](#open-questions)
- [Users & Permissions](#users--permissions)

---

## Current Status

**Active milestone: Milestone 3 — Integrate MyStudio into chat UI**

| Milestone | Status |
|-----------|--------|
| 1 — LineLeader login + GBS/JR GBS tour pull + reschedule | ✅ Complete |
| 2 — MyStudio login + 2FA + full daily schedule | ✅ Complete (2026-06-01) |
| 3 — Integrate MyStudio into chat UI + mock chatbot | 🔄 In Progress |
| 4 — Move / create / cancel appointments | ⬜ Not started |
| 5 — Chat UI + Claude API + function calling + Excel export | ✅ Complete |
| 6 — Employee schedule generator (stretch goal) | ⬜ Not started |

### Milestone 2 — COMPLETE (2026-06-01)

**Full MyStudio integration: login + 2FA + schedule + student roster all working.**

#### Files created/updated:
- `sites/mystudio/auth.py` — **COMPLETE REWRITE** (cookie-based auth, not bearer tokens)
- `sites/mystudio/schedules.py` — **COMPLETE REWRITE** (real confirmed endpoints)
- `sites/mystudio/appointments.py` — Updated with real API fields
- `config/settings.py` — Fixed MyStudio URLs, added hardcoded company/user IDs
- `mock_chatbot.py` — Updated StudentAppointment mock to match new fields
- `chatbot.py` — Updated to call synchronous `get_todays_appointments()`
- `format_tours.py` — Updated unified schedule formatter for new `parent_name` field

#### Critical architectural discovery:
**MyStudio uses session-based auth (PHP cookies), NOT bearer tokens.**
- `c_u_id_9901`, `c_u_id_9901_sessid`, `PHPSESSID` are the session cookies
- No Authorization header needed — cookies carry the session
- `remember_me: true` in OTP POST → cookies persist 30 days
- Cookie cache file: `browser_state/mystudio_cookies.json`
- Session validity checked via `GET /Api/PortalApi/verifySession`

#### Confirmed MyStudio API endpoints (from Playwright network capture 2026-05-31):
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /Api/PortalApi/login` | POST | Step 1: credentials → triggers OTP email |
| `POST /Api/PortalApi/login` | POST | Step 2: OTP verification → sets session cookies |
| `GET /Api/PortalApi/verifySession` | GET | Check if session is still valid |
| `GET /Api/PortalApi/getClassScheduledetails` | GET | Today's class time slots |
| `POST /Api/PortalApi/getClassdatatabledetails` | POST | Student roster for a time slot |

**All URLs are at `https://cn.mystudio.io/v43/Api/PortalApi/`**

#### Confirmed IDs (Code Ninjas Eastvale Chino — hardcoded in settings.py):
- `company_id = "578"`
- `user_id = "9901"` (the logged-in user ID)
- login email = `eastvalechinocodeninjas@gmail.com`

#### Login flow (confirmed from real browser capture):
1. `POST /login` with `{"email": "...", "password": BASE64("actual_password"), "from": "login_form"}`
2. Server responds `{"status": "Success", "msg": "One time passcode has been send to..."}` and sends OTP email
3. `POST /login` with `{"otpCode": BASE64("6_digit_code"), "from": "otp_form", "remember_me": true, ...}`
4. Server responds with full company/user JSON + sets session cookies
5. All subsequent API calls use those cookies — no Authorization header

#### Schedule fetch flow:
1. `GET getClassScheduledetails?company_id=578&selected_date=2026-06-01&class_scheduler_verion=2&view_roster_flag=N`
   - Returns list of class types (e.g., "CREATE (CODING)", "JR") with time slots
   - Each slot has: `class_appointment_times_id`, `start_time`, `reg_count_time`, `capacity_value`
2. For each slot with `reg_count_time > 0`: `POST getClassdatatabledetails` (form-encoded, DataTables format)
   - Returns student records with: `Participant` (student name), `Buyer` (parent name), `Phone`, `rank_status`, `end_time`, `class_reg_id`

#### StudentAppointment fields (from real API):
| Field | Source |
|-------|--------|
| `id` | `class_reg_id` |
| `student_name` | `Participant` |
| `student_id` | `student_id` |
| `parent_name` | `Buyer` |
| `phone` | `Phone` |
| `rank` | `rank_status` (e.g., "White Belt") |
| `appointment_type` | class title from schedule (e.g., "CREATE (CODING)", "JR") |
| `start_time` | from slot `start_time` field |
| `end_time` | from `end_time` in student record (e.g., "2026-06-01 16:00:00") |

#### What's confirmed working (2026-06-01):
- ✅ Direct API login with OTP 2FA — `sites/mystudio/auth.py`
- ✅ Session cookie caching (30 days) — `browser_state/mystudio_cookies.json`
- ✅ Auto-login on second run — loads cached cookies, no OTP needed
- ✅ `getClassScheduledetails` — returns all class types + time slots
- ✅ `getClassdatatabledetails` — returns student roster for each time slot
- ✅ Full daily schedule parsing — 27 students across 9 time slots (example output)
- ✅ Test script `test_updated_schedules.py` shows all time slots with students

#### Key fix (what made roster work):
The API requires the **full DataTables request with all 23 column definitions**, not just minimal form data.
Previously we were sending:
```python
{"draw": "1", "company_id": "578", "class_appointment_times_id": "27389", ...}  # ❌ 500 error
```
Now sending:
```python
{
  "draw": "1",
  "columns[0][data]": "",
  "columns[1][data]": "show_icon",
  "columns[2][data]": "Participant",
  ...
  "columns[22][data]": "",
  # ... all 23 columns defined
}  # ✅ 200 OK, data returned
```

#### Auth details confirmed:
- Login email: `eastvalechinocodeninjas@gmail.com` (set in `.env` as `MYSTUDIO_USERNAME`)
- Password encoding: `base64(urllib.parse.quote(password, safe=''))` — the `safe=''` is critical (encodes `@` as `%40`)
- OTP encoding: same `base64(urllib.parse.quote(otp, safe=''))` 
- Gmail App Password: NOT available (Google Workspace corp account — app passwords disabled by admin)
- OTP flow: manual entry in terminal (user checks email, types 6-digit code)
- Cookie file: `browser_state/mystudio_cookies.json`
- Session cookies: `PHPSESSID`, `c_u_id_9901_sessid`, `ms_trace_id`, `ms_u_em`
- Note: `c_u_id_9901` cookie not appearing in direct API login (only in browser flow) — session still works via `verifySession`

#### Known issue to watch for:
The `getClassdatatabledetails` POST previously returned 500 errors when called from Python requests directly (before Playwright session extraction). The fix is the Playwright-extracted cookies. If it still 500s, check:
- Are all cookies being set? Print `session.cookies.get_dict()` after `get_session()`
- Is `X-Requested-With: XMLHttpRequest` header present? (Required for this endpoint)
- Is Content-Type `application/x-www-form-urlencoded`? (Not JSON)

### Milestone 1 — What's built
- `get_todays_sessions()` — fetches today's Tours via action-items API, filters `display_type == "Tour"`
- `enrich_sessions_with_children()` — two-step family lookup to add child names, ages, and JR GBS fallback
- `reschedule_tour()` — GET task → normalize payload → confirm → PUT with new `due_date_time`
- `run_milestone1.py` — interactive CLI: show schedule table → optionally reschedule by number or name

**`GBSSession` fields:**
| Field | Source |
|-------|--------|
| `student_name` | Guardian first + last name (action-items) |
| `start_time` | `date_time` converted from UTC |
| `tour_type` | `"GBS"` or `"JR GBS"` — description field, then `custom_values JUNIOR` fallback |
| `display_type` | Raw `display_type` from API (always `"Tour"` after filtering) |
| `description` | Free-text notes (`"GBS"`, `"JR GBS"`, or blank) |
| `item_id` | Task ID — used for GET/PUT reschedule calls |
| `assignee_name` | Staff member name |
| `family_id` | Populated by enrichment |
| `child_names` | Plain list for fuzzy matching — populated by enrichment |
| `child_display` | `"Name (Xy)"` list for table display — populated by enrichment |

### Milestone 5 — Chat UI + Multi-Provider Claude API with Function Calling
- **`llm_provider.py`** — Multi-provider abstraction (Claude, Ollama, extensible for others)
- `app.py` — Flask web server on port 5001 (routes: GET `/`, POST `/api/chat`, GET `/api/audit-log`, GET `/api/export/tours`)
  - Instantiates provider based on `LLM_PROVIDER` env var (defaults to Claude)
  - Passes provider to ChatbotEngine
- `chatbot.py` — ChatbotEngine class (provider-agnostic) with agentic loop and three tools:
  - `get_todays_gbs_tours` — fetch today's tours from LineLeader
  - `get_tour_details` — get details for a specific tour
  - `reschedule_tour` — reschedule a tour to new time
- `mock_chatbot.py` — MockChatbotEngine for testing without API costs (activated with `TEST_MODE=true`)
- `test_chatbot.py` — Interactive CLI chatbot test harness (works with any provider)
- `format_tours.py` — Format tour data as nested bullets with emojis
- `export_tours.py` — Generate Excel files with proper formatting (parent, children, tour type, staff columns)
- `audit_log.py` — JSON-based audit logging to `logs/audit.jsonl` (one JSON object per line)
- Inline HTML/CSS/JavaScript in app.py with Code Ninjas branding (logo, colors)

**Key features:**
- Web UI accessible from any machine on same WiFi (bound to 0.0.0.0:5001)
- Claude Haiku 4.5 model for cost efficiency
- Real-time nested bullet format with emojis for readability
- Excel export with parent/children/tour type/staff columns
- Markdown link parsing for clickable download links
- Audit trail of all interactions (JSON lines format)
- Mock chatbot for testing without burning API tokens

**How to run (three ways):**

| Mode | Command | Cost | Speed | Tools | Best For |
|------|---------|------|-------|-------|----------|
| **Claude** | `python3 app.py` | ~$0.001-0.005/query | <1 sec | ✅ Full | Production, development |
| **Ollama** | `LLM_PROVIDER=ollama python3 app.py` | Free | 2-5 sec | ⚠️ Limited | Cost-free testing (chat-only) |
| **Mock** | `TEST_MODE=true python3 app.py` | Free | Instant | ✅ Simulated | UI testing, no API calls |

Navigate to **http://localhost:5001** or **http://<your-ip>:5001** from another machine.

**Requirements:**
- Claude mode: Requires `ANTHROPIC_API_KEY` in `.env`
- Ollama mode: Requires `ollama serve` running in another terminal
- Mock mode: No external services needed

---

## Multi-Provider LLM Architecture

**Key Innovation:** The chatbot is **provider-agnostic**. It can work with any LLM via a clean abstraction layer.

### The Provider System (llm_provider.py)

The `llm_provider.py` module provides:

**1. LLMProvider (Abstract Base Class)**
```python
class LLMProvider(ABC):
    @abstractmethod
    def call(messages, system_prompt, tools) -> Dict:
        """Call the LLM, return standardized response."""
```

**2. Implementations**
- `ClaudeProvider` — Anthropic SDK, full tool support ✅
- `OllamaProvider` — OpenAI-compatible API, limited tool support ⚠️

**3. Unified Response Format**
All providers return the same structure:
```python
{
    "type": "tool_use" | "end_turn",     # What the LLM is doing
    "content": str | dict,                # Text or tool info
    "raw": <original_response>            # For debugging
}
```

### How It Works

1. **Environment-driven selection** — `LLM_PROVIDER=claude` or `LLM_PROVIDER=ollama`
2. **Factory pattern** — `get_provider()` creates the right instance
3. **Injected into ChatbotEngine** — `ChatbotEngine(provider=provider)`
4. **Identical agentic loop** — Same tool calling flow for all providers

### Adding a New Provider

To add support for a new LLM (e.g., Google Gemini):

```python
# In llm_provider.py
class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def call(self, messages, system_prompt, tools):
        # Translate to Gemini API format
        response = self.client.messages.create(...)
        
        # Return standardized format
        if response.contains_tool_calls():
            return {"type": "tool_use", "content": {...}}
        else:
            return {"type": "end_turn", "content": text}
```

Then update `get_provider()` to handle the new option:
```python
elif provider_name == "gemini":
    return GeminiProvider(api_key=os.getenv("GEMINI_API_KEY"))
```

**The beauty:** ChatbotEngine doesn't change. The agentic loop works identically for Gemini, Claude, or any future provider.

---

## Project Structure

```
cnec-chatbot/
├── CLAUDE.md                        ← you are here
├── CNEC-Chatbot-Requirements.md     ← full requirements doc
├── README.md                        ← general project overview
├── README_CHATBOT.md                ← how to use the chatbot UI
├── run_milestone1.py                ← Milestone 1 CLI entry point
├── app.py                           ← Milestone 5: Flask web server (port 5001)
├── chatbot.py                       ← Milestone 5: Claude API + function calling
├── mock_chatbot.py                  ← Milestone 5: Mock chatbot (TEST_MODE=true)
├── test_chatbot.py                  ← Milestone 5: Interactive CLI test tool
├── format_tours.py                  ← Milestone 5: Format as nested bullets + emojis
├── export_tours.py                  ← Milestone 5: Generate Excel files
├── audit_log.py                     ← Milestone 5: JSON audit logging
├── requirements.txt
├── config/
│   └── settings.py                  ← ALL config lives here
├── core/
│   └── logger.py                    ← shared structured JSON logging
├── sites/
│   └── lineleader/
│       ├── auth.py                  ← login + Bearer token management
│       └── schedules.py             ← API calls, session parsing, reschedule
├── asset/
│   └── cnec-logo.jpeg               ← Code Ninjas Eastvale Chino logo
├── logs/
│   ├── cnec_chatbot.log             ← structured JSON logs
│   └── audit.jsonl                  ← audit trail (one JSON object per line)
├── exports/                         ← Excel files saved here
└── browser_state/
    └── lineleader_token.json        ← cached Bearer token + expiry
```

Future milestones add:
- `sites/mystudio/` — MyStudio automation (Milestone 2)
- `sites/homebase/` — Homebase API (Milestone 3)

---

## Environment Variables

All credentials and configuration live in `.env` (copy from `.env.example`). Critical variables:

| Variable | Purpose | Required For | Example |
|----------|---------|--------------|---------|
| `LINELEADER_USERNAME` | LineLeader/ChildCareCRM login | Milestone 1 + all | `user@codeninjas.com` |
| `LINELEADER_PASSWORD` | LineLeader password | Milestone 1 + all | (password) |
| `ANTHROPIC_API_KEY` | Claude API access | Milestone 5 (real mode) | `sk-ant-...` |
| `LLM_PROVIDER` | Which LLM backend to use | Milestone 5 | `claude` or `ollama` |
| `CLAUDE_MODEL` | Which Claude model | Milestone 5 (Claude mode) | `claude-haiku-4-5` |
| `OLLAMA_BASE_URL` | Ollama server URL | Milestone 5 (Ollama mode) | `http://localhost:11434/v1` |
| `OLLAMA_MODEL` | Which Ollama model | Milestone 5 (Ollama mode) | `mistral` |

**Important:**
- `.env` is git-ignored (never commit it)
- Copy `.env.example` and fill in real values
- Test mode (`TEST_MODE=true`) needs NO credentials

---

## Three Sites

| ID | Platform | URL | Auth |
|----|----------|-----|------|
| Site 1 | MyStudio | cn.mystudio.io | Username + password + email 2FA |
| Site 2 | LineLeader / ChildCareCRM | login.lineleader.com | OAuth2 PKCE (no 2FA) |
| Site 3 | Homebase | app.joinhomebase.com | Homebase API — runtime prompt only, never saved |

---

## Site 2 — LineLeader Architecture (Milestone 1)

### Key discovery: It's actually ChildCareCRM
LineLeader was acquired by ChildCareCRM. After login it redirects to
`my.childcarecrm.com`. The API lives at `live.childcarecrm.com/api/v3/`.

### Auth flow (OAuth2 with PKCE)
```
Playwright submits login form at login.lineleader.com
    ↓
OAuth2 PKCE flow runs automatically (CSRF tokens + code challenges)
    ↓
Browser lands on my.childcarecrm.com
    ↓
App calls live.childcarecrm.com/api/v3/sso/login → returns Bearer JWT
    ↓
We intercept that response and extract the Bearer token
    ↓
Token saved to browser_state/lineleader_token.json with expiry
    ↓
All subsequent API calls use requests (no browser) with Bearer token
```

Why Playwright for login: The PKCE flow uses server-generated CSRF tokens and
cryptographic code challenges — can't replicate with raw requests.

### Confirmed API endpoints
All at `https://live.childcarecrm.com/api/v3/`:

| Endpoint | Purpose |
|----------|---------|
| `POST /sso/login` | Validates session, returns Bearer JWT |
| `GET /action-items?task_dash_dates[0]=today&org_id=101178` | Today's sessions |
| `GET /action-items?task_dash_dates[0]=future&org_id=101178` | Upcoming sessions |
| `GET /tasks/{item_id}` | Fetch full task object (needed before PUT) |
| `PUT /tasks/{item_id}` | Update a task (reschedule, cancel, etc.) |
| `GET /families/{family_id}` | Full family record including children[] |
| `GET /staff/58347` | Logged-in user info |
| `GET /centers/102025` | Center details |
| `GET /centers/102025/classrooms` | Classrooms |
| `GET /families/recent?org_id=101178` | Recent families |

### Confirmed write endpoint — reschedule a Tour
Captured via Chrome DevTools on 2026-05-27.

```
PUT https://live.childcarecrm.com/api/v3/tasks/{item_id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body (full object required — PUT not PATCH):**
```json
{
  "id": 2003102,
  "family": 929179,
  "type": 89,
  "assigned_to_staff": 58347,
  "assigned_by_user_id": 58347,
  "due_date_time": "2026-05-28T04:30:00Z",
  "description": "",
  "is_completed": false,
  "completed_by_user_id": null,
  "completed_date_time": null,
  "result_type": null,
  "result_description": "",
  "is_canceled": false,
  "duration": 30
}
```

**Key fields:**
- `due_date_time` — ISO 8601 UTC — this is the field we change to reschedule
- `type: 89` — confirms task_type_id 89 = Tour (GBS)
- `family` — family ID integer
- `duration` — session length in minutes (30 default)
- Full object must be sent (GET first, then modify `due_date_time`, then PUT)

**Reschedule flow (implemented in Milestone 1):**
1. `GET /api/v3/tasks/{item_id}` — fetch current full task object
2. Normalize expanded objects → plain IDs via `_build_put_payload()` (GET returns `family: {id, ...}` but PUT expects `family: 929179`)
3. Swap `due_date_time` to new UTC value (convert local → UTC before sending)
4. Show confirmation prompt to user before writing
5. `PUT /api/v3/tasks/{item_id}` with normalized payload

Implemented in `sites/lineleader/schedules.py` → `reschedule_tour()`.

### Confirmed org/center IDs
- `org_id = 101178` (Code Ninjas Eastvale Chino)
- `center_id = 102025`
- `staff_id = 58347`

### Confirmed action-items response structure
```json
{
  "items": [
    {
      "item_type": "task",
      "item_id": "1995970",
      "guardian_first_name": "Keadrick",
      "guardian_last_name": "Washington",
      "display_type": "Tour",
      "assignee_first_name": "Venay",
      "assignee_last_name": "Bhatia",
      "assignee_id": "58347",
      "location_name": "Eastvale-Chino, CA",
      "date_time": "2026-05-26T22:00:00+00:00",
      "description": "JR GBS",
      "task_type_id": 89,
      "task_group_id": 4
    }
  ],
  "counts": { "today": 7, "future": 25, "past": 580, "total": 612 }
}
```

### Filtering: GBS Tours only
Filtered in `_parse_single_item` by `display_type == "Tour"`. All Tours are GBS Tours.

### Tour Type: GBS vs JR GBS
Two types of tours exist. Determined in this priority order:
1. `description` field on action-items — contains `"JR"` → JR GBS, otherwise GBS
2. Family `custom_values` fallback (if description is blank) — value `"JUNIOR"` → JR GBS

Stored in `GBSSession.tour_type` = `"GBS"` or `"JR GBS"`.

### Child Names, Ages & Family Enrichment
The action-items response only returns the **guardian** (parent) name, not the child's name.
Child names require a two-step lookup after fetching sessions:
1. `GET /tasks/{item_id}` → `family.id`
2. `GET /families/{family_id}` → `children[]`

Implemented in `enrich_sessions_with_children()` — called in the runner after `get_todays_sessions()`.
Adds ~2 API calls per session. Fine for 3-5 tours/day.

**Key finding:** Child's last name often differs from guardian's last name
(e.g. Wittie Hughes → child: Journei Ashbourne age 4). Child name matching is essential
for natural language queries like "reschedule Journei's tour".

**`GBSSession` fields populated by enrichment:**
| Field | Type | Purpose |
|-------|------|---------|
| `family_id` | `str` | ChildCareCRM family ID |
| `child_names` | `List[str]` | Plain names only — used for fuzzy name matching |
| `child_display` | `List[str]` | `"Name (Xy)"` format — used for table display |

**Age extraction:** Calculated from `children[].date_of_birth` (ISO date string) using
`_calculate_age()`. Displayed as `"Journei Ashbourne (4y)"` in the schedule table.
Safety net: staff can spot a young child tagged as GBS and verify the tour type.

**Name matching** (`_name_matches` in runner): checks guardian name AND all child names,
case-insensitive substring. e.g. `"Journei"`, `"Ashbourne"`, `"Wittie"` all match Wittie Hughes' tour.

### Family record structure (confirmed from live API)
```json
{
  "id": 931306,
  "primary_guardian": {
    "first_name": "Wittie", "last_name": "Hughes",
    "email": "wittiehughes@gmail.com",
    "primary_phone": { "number": "(415) 815-9602" },
    "relation_to_child": "Mother"
  },
  "children": [
    {
      "id": 943521,
      "first_name": "Journei", "last_name": "Ashbourne",
      "date_of_birth": "2021-12-09",
      "status": { "name": "Tour Scheduled" }
    }
  ],
  "custom_values": [
    {
      "custom_value_group": { "values": { "value": "Lead Path" } },
      "custom_values": [ { "values": { "value": "JUNIOR" } } ]
    }
  ]
}
```

### Login form selectors (confirmed)
- Username: `#username` (name="_username")
- Password: `#password` (name="_password")
- Submit: `button[type="submit"]`

---

## Architecture Decision Log

A running record of significant decisions, in the order they were made.
Update this whenever the architecture changes. Each entry explains what
changed, why, and what was ruled out.

---

### ADR-001 — Playwright for browser automation
**Date:** May 2026 | **Milestone:** 1

**Decision:** Use Playwright (not Selenium) for all browser automation.

**Reason:** API interception is first-class in Playwright. Session caching
(storage_state) is built in. Native async support. Cross-platform Mac + Windows.

**Ruled out:** Selenium (no native interception), Puppeteer (Python wrapper is unstable).

---

### ADR-002 — Original plan: Playwright interception for all data fetching
**Date:** May 2026 | **Milestone:** 1

**Decision (original):** Navigate to schedule pages and intercept internal
XHR/fetch API calls to capture JSON responses.

**Superseded by ADR-003.**

---

### ADR-003 — Hybrid: Playwright login → direct requests for all API calls
**Date:** May 2026 | **Milestone:** 1

**Decision:** Use Playwright ONLY for login. Extract Bearer JWT from the
`/api/v3/sso/login` response. Use Python `requests` for all subsequent API calls.

**What triggered this:** Live site inspection revealed LineLeader is actually
ChildCareCRM and exposes a full REST API at `live.childcarecrm.com/api/v3/`.
No need to keep a browser open for data fetching.

**Why Playwright is still needed for login:** The login uses OAuth2 PKCE with
server-generated CSRF tokens and cryptographic code challenges across a
multi-step redirect chain. Cannot be replicated with raw requests reliably.

**Why this is better than pure interception:**
- No browser sitting open waiting for page loads
- API calls don't depend on UI navigation or DOM structure
- Easy to add date filters, pagination, etc.
- Much easier to test and debug

**Token lifecycle:**
- Bearer JWT expires ~1 hour (parsed from JWT exp claim)
- Cached to browser_state/lineleader_token.json with expiry
- On each run: load from cache if valid, re-login only when expired
- 5-minute buffer before expiry prevents mid-session token death

---

### ADR-004 — Direct API strategy for all sites where possible
**Date:** May 2026 | **Milestone:** 1 (forward-looking)

**Decision:** For every new site, investigate REST API first before building
DOM scraping. Use hybrid pattern (Playwright login → requests) wherever possible.

**Action for Milestone 2:** Before writing any MyStudio scraping code, log in
manually in Chrome, open DevTools Network tab, look for JSON API calls.
Document any discovered endpoints in this file before writing code.

---

### ADR-005 — Config-driven design for multi-tenant SaaS future
**Date:** May 2026 | **Milestone:** 1

**Decision:** All center-specific values live in config/settings.py loaded
from .env. Zero hardcoded values in site modules.

**Values that must stay in settings.py (never in site modules):**
- LINELEADER_ORG_ID = "101178"
- All URLs and API base paths

**To deploy for another Code Ninjas center:** update .env and IDs in
settings.py only. No other files need changes.

---

### ADR-006 — Flask + Claude API for Milestone 5 Chat UI
**Date:** May 2026 | **Milestone:** 5

**Decision:** Build web UI with Flask (Python) + inline HTML/CSS/JavaScript.
Use Claude Haiku 4.5 with function calling for orchestration. Mock chatbot 
for testing without API costs.

**Why Flask:** Minimal overhead, leverage existing Python codebase, no separate 
frontend build needed.

**Why Claude + function calling:** Claude handles natural language understanding 
and agentic loop. Tool definitions map to Milestone 1 functions (get_todays_sessions, 
reschedule_tour, etc.). Cleaner than writing conditional logic.

**Why Haiku:** 80% cheaper than Opus, sufficient for schedule extraction/filtering 
tasks. Switching to Opus easy if complexity increases.

**Why mock chatbot:** During development, test entire UI without consuming API 
tokens. Set TEST_MODE=true to activate. Real mode uses Claude API.

**Parent vs Assignee fix:** Initially all parent names showed as "Venay Bhatia" 
(staff). Root cause: Claude tool output mixed guardian and assignee names 
ambiguously. Solution: Explicit labels in tool result output:
```
Parent: {guardian} | Children: {child_names} | Type: {tour_type} | Staff: {assignee}
```
Claude now parses correctly and formats as nested bullets.

---

---

## Claude API Models & Pricing

**Current choice:** `claude-haiku-4-5` (cost-optimized)

### Available Models
| Model | Input/1M | Output/1M | Best For | Context |
|-------|----------|-----------|----------|---------|
| Haiku 4.5 | $1 | $5 | Simple extraction, function calling | 200K |
| Sonnet 4.6 | $3 | $15 | Complex reasoning, balance | 200K |
| Opus 4.8 | $5 | $25 | Maximum intelligence | 200K |

### Free Tier Option
Anthropic offers **$5 free credits** when you sign up. To try:
1. Create account at https://console.anthropic.com
2. Generate API key
3. Add to `.env` as `ANTHROPIC_API_KEY`
4. Test with `TEST_MODE=true python3 app.py` first (uses mock, no cost)

### Switching Models
In `chatbot.py`, line 68, change:
```python
model="claude-haiku-4-5",  # Change this line
```

To:
```python
model="claude-sonnet-4-6",  # Higher capability, higher cost
model="claude-opus-4-8",     # Best reasoning, highest cost
```

**Why Haiku for this project:** Simple data extraction (list tours, filter by type) doesn't need Opus intelligence. Haiku is 80% cheaper and handles it fine. If Milestone 2–3 add complex reasoning, upgrade to Sonnet.

### Cost Estimate (Claude API)
- Haiku: ~$0.001–0.005 per "show schedule" query
- Sonnet: ~$0.003–0.015 per query
- Opus: ~$0.005–0.025 per query

### Alternative: Ollama (Free, Local, No API Key Needed)

Run LLMs locally on your machine for **zero cost**. Perfect for development and testing.

**Why Ollama?**
- Completely free (no API costs)
- Runs entirely on your machine (private)
- Full tool calling support (same agentic loop as Claude)
- Slower than Claude (~2-5 seconds per response vs. <1 second), but functional for development
- Great for testing without consuming API credits

#### Installation & Setup

**1. Install Ollama**
```bash
# Download from https://ollama.ai
# Then run the installer
# Verify installation:
ollama --version
```

**2. Start Ollama server**
```bash
ollama serve
# This starts the OpenAI-compatible API on http://localhost:11434
# Keep this terminal open while using the chatbot
```

**3. Pull a model (in another terminal)**
```bash
ollama pull mistral
# Choose from: mistral, neural-chat, llama2, dolphin-mixtral
# First pull takes ~5-10 min (depends on model size + internet)
```

#### Configuration

Add to `.env`:
```
LLM_PROVIDER=ollama
OLLAMA_MODEL=mistral
OLLAMA_BASE_URL=http://localhost:11434/v1
```

Or use environment variables:
```bash
LLM_PROVIDER=ollama OLLAMA_MODEL=neural-chat python3 app.py
```

#### Running with Ollama

**Web UI (with Ollama backend):**
```bash
# Terminal 1: Start Ollama server
ollama serve

# Terminal 2: Run the app
LLM_PROVIDER=ollama python3 app.py
# Navigate to http://localhost:5001
```

**CLI chatbot (with Ollama backend):**
```bash
LLM_PROVIDER=ollama python3 test_chatbot.py
```

**Recommended Ollama models:**
| Model | Size | RAM | Speed | Notes |
|-------|------|-----|-------|-------|
| `mistral` | 7B | 4GB | Fast | Best for instructions, good balance |
| `neural-chat` | 7B | 4GB | Fast | Optimized for chat, friendly responses |
| `llama2` | 7B | 4GB | Fast | General purpose, safe |
| `dolphin-mixtral` | 47B | 20GB | Slower | More capable, requires more resources |

**Performance comparison:**
| Provider | Speed | Cost | Setup |
|----------|-------|------|-------|
| Claude (Haiku) | <1 sec | $0.001-0.005/query | API key only |
| Ollama (mistral) | 2-5 sec | Free | Download + run locally |
| Mock chatbot | Instant | Free | None |

#### Ollama Limitations ⚠️

**CRITICAL:** Ollama has inconsistent tool calling support. While the chatbot is designed to work with Ollama, real-world testing shows that Ollama models (including Mistral) often ignore tool definitions and don't call functions reliably.

**What breaks with Ollama:**
- `get_todays_tours()` — doesn't call the tool, asks user to describe tours instead
- `reschedule_tour()` — doesn't call the tool reliably
- `get_tour_details()` — inconsistent results

**Workaround:** Use `TEST_MODE=true` for cost-free, reliable testing without Ollama. Mock mode provides instant feedback and zero API costs.

#### Comparison: Which to Use

| Use Case | Command | Notes |
|----------|---------|-------|
| **Development (fastest)** | `TEST_MODE=true python3 app.py` | Instant, no API keys, no setup |
| **Development (real data)** | `python3 app.py` | Real Claude, costs ~$0.001-0.005/query |
| **Production** | `python3 app.py` | Claude API, reliable tool calling, ~$0.001-0.005/query |
| **Free local testing** | Don't use Ollama | Tool calling doesn't work; use mock mode instead |

#### Switching Between Providers

For complete examples, see [How to Run](#how-to-run) → [Milestone 5: Web Chat UI](#milestone-5-web-chat-ui).

---

## Safety & Design

### Safety Rules (Non-Negotiable)

From requirements §8:
- **Never write to a live site without explicit user confirmation** — reschedule, cancel, create always require user approval
- Any function that modifies data must have a confirmation step before executing
- Ambiguous input → stop and ask, never assume
- Unexpected site state → halt, do not touch anything, report to user

### Design Principles

- ✅ **Multi-tenant ready** — zero hardcoded values, everything in `config/settings.py` loaded from `.env`
- ✅ **Config-driven** — to deploy for another Code Ninjas center, update `.env` and org/center IDs only
- ✅ **Token caching** — Bearer tokens cached ~1 hour with 5-minute safety buffer
- ✅ **Audit trail** — all interactions logged to `logs/audit.jsonl` (JSON lines format)
- ✅ **No credential storage** — Homebase credentials entered at runtime, never saved

### Config Philosophy

Everything center-specific lives in `config/settings.py` loaded from `.env`.
No hardcoded values in site modules. To deploy for another Code Ninjas center:
update `.env` and the org/center IDs in `settings.py` only.

### Credentials Strategy

| Site | Storage |
|------|---------|
| LineLeader (Site 2) | `.env` file |
| MyStudio (Site 1) | `.env` file |
| Microsoft Graph (2FA) | `.env` file |
| Homebase (Site 3) | Runtime prompt ONLY — never saved to disk |

Homebase credentials must never be stored. Owner enters them at runtime.
They are held in memory for the session only.


---

## Dependencies & Setup

### Initial Setup (One-Time)

```bash
# 1. Clone and navigate
git clone https://github.com/codeninjaseastvalechino/cnec-chatbot.git
cd cnec-chatbot

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # or: .venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers
playwright install chromium

# 5. Create .env from template
cp .env.example .env
# Edit .env and fill in LINELEADER_USERNAME, LINELEADER_PASSWORD, etc.
```

### Dependency Versions

Listed in `requirements.txt` with version constraints (>=). Pinned versions only if stability issues arise.

```
playwright>=1.44.0    # browser automation (login only)
requests>=2.31.0      # direct API calls (data fetching)
python-dotenv>=1.0.0  # .env loading
anthropic>=0.25.0     # Claude API (Milestone 5 web UI)
flask>=3.0.0          # web server (Milestone 5)
openpyxl>=3.1.0       # Excel export (Milestone 5)
apscheduler>=3.10.0   # scheduled runs (Milestone 6 — future)
rich>=13.7.0          # terminal output formatting
openai>=1.0.0         # OpenAI SDK (Ollama compatibility)
```

### Dependency Management

**Updating dependencies:**
```bash
# Update all dependencies to latest compatible versions
pip install --upgrade -r requirements.txt

# Update a specific package
pip install --upgrade anthropic
```

**Playwright version note:** If you encounter browser automation issues, reinstall:
```bash
playwright install chromium --with-deps
```

---

## How to Run

### Prerequisite: Setup
Before running any milestone, complete "Dependencies & Setup" above (one-time).

Verify setup:
```bash
source .venv/bin/activate
python3 -c "import playwright; import requests; import anthropic; print('✅ Setup OK')"
```

---

### Milestone 1: CLI Tool (GBS Tours + Reschedule)

**Prerequisites:** LineLeader credentials in `.env`

```bash
source .venv/bin/activate
python3 run_milestone1.py
```

**What it does:**
1. Logs in to LineLeader (headless by default, token cached ~1 hour)
2. Fetches today's Tours and displays formatted table with child names/ages
3. Prompts: "Reschedule a tour? (y/n)"
4. If yes: enter by tour number (e.g. `1`) or name (e.g. `Journei`)
5. If ambiguous name match: shows 2–3 choices, ask to be more specific
6. Confirmation prompt before writing to the API

**Exit codes:**
- `0` — success
- `1` — missing .env credentials or API error
- `2` — login failure (check credentials, token cache may be stale)

---

### Milestone 5: Web Chat UI

Choose one based on your needs:

#### Option A: Mock Mode (Zero API Costs) ← Best for Development
```bash
source .venv/bin/activate
TEST_MODE=true python3 app.py
```

**Prerequisites:** None (no API keys needed)

**What it does:**
- Starts Flask server on `http://localhost:5001`
- Uses `MockChatbotEngine` (instant responses, no API calls)
- Test full UI without burning Claude credits
- Perfect for UI iteration and debugging

**Access:** `http://localhost:5001` (local machine) or `http://<your-ip>:5001` (other machines)

---

#### Option B: Claude API Mode (Real Data)
```bash
source .venv/bin/activate
python3 app.py
```

**Prerequisites:** `ANTHROPIC_API_KEY` in `.env`

**What it does:**
- Starts Flask server on `http://localhost:5001`
- Uses real Claude API + real LineLeader data
- Claude Haiku 4.5 with function calling
- Excel download support via `/api/export/tours`
- Audit logging to `logs/audit.jsonl`

**Cost:** ~$0.001–0.005 per query (Haiku model)

---

#### Option C: Ollama Mode (Free Local LLM) ⚠️ Limited
```bash
# Terminal 1: Start Ollama server
ollama serve

# Terminal 2: Run the app
source .venv/bin/activate
LLM_PROVIDER=ollama python3 app.py
```

**Prerequisites:** Ollama installed + running, `OLLAMA_MODEL` in `.env`

**⚠️ Important Limitation:** Ollama has inconsistent tool calling support. Use Option A (mock) instead for cost-free testing.

See [Ollama Limitations](#ollama-limitations) for details.

---

### Chatbot Engine Testing (No Web UI)

Debug the chatbot engine directly without Flask:

```bash
source .venv/bin/activate
python3 test_chatbot.py
```

**What it does:**
- Interactive CLI chat with `ChatbotEngine` or `MockChatbotEngine`
- Useful for debugging tool responses
- Type natural language queries and see results immediately
- Type `quit` to exit

**Use this for:**
- Testing Claude tool calling without web overhead
- Debugging specific NLP queries
- Iterating on chatbot logic

---

## Development Commands

### Clear Cached Token (Force Fresh Login)
```bash
rm -f browser_state/lineleader_token.json
python3 run_milestone1.py
```

Token is cached for ~1 hour (5-minute safety buffer before expiry). Use this if:
- Login hangs or fails
- Credentials were updated
- Suspicious behavior (seeing old data)

---

### View Structured Logs
All operations are logged to `logs/cnec_chatbot.log` as JSON (one record per line).

View in real-time:
```bash
tail -f logs/cnec_chatbot.log | jq .
```

Grep for errors:
```bash
grep '"level": "ERROR"' logs/cnec_chatbot.log | jq .
```

Filter by module:
```bash
cat logs/cnec_chatbot.log | jq 'select(.module == "sites.lineleader.auth")'
```

**Log levels:**
- File: `DEBUG+` (all messages)
- Console: `INFO+` (only important messages)

---

### Logging in Code
See `core/logger.py`. Pattern:

```python
from core.logger import get_logger

logger = get_logger(__name__)
logger.info("Starting session")
logger.error("API call failed: %s", error_msg)
```

---

### Debug Mode — Watch the Playwright Browser Login
Edit `config/settings.py`:
```python
BROWSER_HEADLESS: bool = False  # Default is True
```

Run as usual:
```bash
python3 run_milestone1.py
```

A Chrome window will appear showing the login flow. Useful for:
- Confirming OAuth2 PKCE flow completes
- Checking for form selector changes
- Diagnosing login errors visually

---

## Debugging & Troubleshooting

### Login Fails
**Symptom:** Exit code 2, or "Invalid credentials" error.

**Debug steps:**
1. Verify `.env` has correct `LINELEADER_USERNAME` and `LINELEADER_PASSWORD`
2. Check credentials manually in a browser at `https://my.childcarecrm.com`
3. Clear token cache: `rm -f browser_state/lineleader_token.json`
4. Enable debug mode (`BROWSER_HEADLESS=False`) to watch the login flow
5. Check `logs/cnec_chatbot.log` for `"level": "ERROR"` entries in `sites.lineleader.auth`

**Common issues:**
- Password changed — update `.env`
- Account locked after failed attempts — wait 5 min, try again
- Playwright version mismatch — run `playwright install chromium`

---

### API Call Fails (404, 500, timeout)
**Symptom:** Error after login succeeds (token is valid).

**Debug steps:**
1. Check `logs/cnec_chatbot.log` — contains request URL, status code, response body
2. Verify `LINELEADER_ORG_ID` and `LINELEADER_CENTER_ID` in `config/settings.py` are correct (currently `101178` and `102025`)
3. Check if the ChildCareCRM API is down (test manually: `curl https://live.childcarecrm.com/api/v3/`)
4. Verify token is fresh (less than 1 hour old): `cat browser_state/lineleader_token.json | jq '.expires_at'`

**Typical flow on error:**
- `get_todays_sessions()` returns empty list or error → no tours to show
- `enrich_sessions_with_children()` fails on a single tour → shows that tour without child names
- `reschedule_tour()` fails → confirmation prompt still shown (safety net)

---

### Token Expired Mid-Session
**Symptom:** "Bearer token invalid" error halfway through a run.

**Details:** Token is cached with expiry (~1 hour from login). A 5-minute safety buffer means re-login happens if token is < 5 min from expiry. If it somehow expires mid-session:

1. Automatic re-login is triggered (Playwright logs in again, new token cached)
2. Operation retries with new token
3. If re-login fails, user is asked to verify credentials

---

### Web UI Not Accessible from Another Machine (Milestone 5)
**Symptom:** Browser on another machine shows "can't reach this site" or "connection refused" when trying to access `http://your-ip:5001`

**Debug steps:**

1. **Verify Flask is running and bound to 0.0.0.0:**
```bash
# On the Mac running the app, you should see:
# * Running on http://0.0.0.0:5001
```

2. **Get your Mac's actual IP address (not broadcast address):**
```bash
hostname -I
# or
ifconfig | grep "inet 192"
# Look for 192.168.x.x where x is 1-254 (NOT .255, NOT 127.0.0.1)
```

3. **From the Windows machine, test connectivity:**
```bash
# Command Prompt on Windows:
ipconfig  # find your Mac's IP
ping 192.168.x.x  # should work if on same network
# Then try: http://192.168.x.x:5001 in browser
```

4. **Allow Python through Mac Firewall:**
   - System Settings → Network → Firewall → Firewall Options
   - Click `+` button
   - Select `/Users/yourname/.venv/bin/python3`
   - Click "Add"

5. **If still blocked, try a different port:**
   - Edit `app.py` line 500:
   ```python
   app.run(host="0.0.0.0", port=8000, debug=True)  # Change 5001 to 8000
   ```
   - Restart Flask
   - Try `http://192.168.x.x:8000`

**Common causes:**
- Mac firewall blocking incoming connections on port 5001
- Getting the broadcast address (.255) instead of actual IP
- Using `localhost` or `127.0.0.1` from another machine (won't work — must use actual IP)
- Different subnets/networks (ping test confirms same network)

---

## Testing

**Current status:** Manual testing only. Unit tests (pytest) planned for Milestone 2+ before adding MyStudio/Homebase.

### Testing Approaches (Manual)

#### 1. CLI Tool — Real LineLeader Data (Milestone 1)
```bash
python3 run_milestone1.py
```

- Tests login flow, API calls, and reschedule functionality
- Requires valid `.env` credentials
- Shows live data from LineLeader
- Exit code indicates success/failure (see [How to Run](#milestone-1-cli-tool-gbs-tours--reschedule))

---

#### 2. Web UI — Mock Data (Milestone 5, Zero Cost)
```bash
TEST_MODE=true python3 app.py
```

- Tests full chat UI without burning Claude API tokens or LineLeader credits
- Uses `MockChatbotEngine` instead of real Claude
- Navigate to `http://localhost:5001` and chat with mock tours
- **Best for:** UI iteration, testing chat flow, debugging without cost

---

#### 3. Web UI — Real Claude + Real Data (Milestone 5, Production)
```bash
python3 app.py
```

- Real Claude API + real LineLeader data
- Requires valid `ANTHROPIC_API_KEY` in `.env`
- Cost: ~$0.001–0.005 per query (Haiku)
- **Best for:** Integration testing, pre-production verification

---

#### 4. Chatbot Engine — Interactive CLI (Milestone 5, Debugging)
```bash
python3 test_chatbot.py
```

- Direct testing of `ChatbotEngine` or `MockChatbotEngine`
- No web UI overhead
- Type queries and see results immediately
- Type `quit` to exit
- **Best for:** Debugging tool responses, testing Claude function calling, rapid iteration

---

### When to Add Unit Tests (Milestone 2+)

Add pytest when:
- Adding MyStudio or Homebase site modules (complex logic, high risk)
- A module has more than one public function (testability needed)
- For critical paths (login with 2FA, reschedule with confirmation, error recovery)

### Unit Testing Strategy (Recommended)

**Framework:** `pytest` + `pytest-asyncio` (we have async Playwright login)

**What to mock:**
- `requests` library (API calls) — use `monkeypatch` or `responses` library
- `Playwright` navigation — avoid testing browser automation directly (too fragile, slow)

**What to test:**
- Auth token caching (expiry, refresh, invalidation)
- Session/tour parsing (data structure integrity)
- Name matching (fuzzy matching edge cases)
- Error recovery (API failures, network timeouts)

**Example fixture:**
```python
@pytest.fixture
def mock_lineleader_api(monkeypatch):
    def _mock(endpoint, response_json):
        def mock_get(*args, **kwargs):
            class MockResponse:
                def json(self): return response_json
                status_code = 200
            return MockResponse()
        monkeypatch.setattr("requests.get", mock_get)
    return _mock
```

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | MyStudio API endpoints | ✅ Confirmed — see Milestone 2 section above |
| 2 | Does MyStudio rate-limit Playwright? | 🔄 Not yet tested — watch for 429 on repeated logins |
| 3 | Homebase API write endpoints for schedule publishing | ✅ Confirmed working |
| 4 | LineLeader write endpoint for rescheduling Tours | ✅ Confirmed — `PUT /api/v3/tasks/{item_id}` |
| 5 | Child name lookup from family record | ✅ Confirmed — `GET /families/{id}` → `children[]` |
| 6 | GBS vs JR GBS distinction | ✅ Confirmed — description field + `custom_values JUNIOR` fallback |
| 7 | Gmail App Password for 2FA extraction | ❌ Not available — Google Workspace corp account. Using manual OTP prompt instead. |
| 8 | Does `remember_me: true` actually persist cookies 30 days? | 🔄 Test — cache to `browser_state/mystudio_cookies.json` |

---

## Users & Permissions

| Role | Access |
|------|--------|
| Owner + Wife | All tasks including employee schedule (Milestone 6) |
| Staff (1 person) | Tasks 1–5 only — employee schedule completely hidden |

Owner identity enforced at session start via PIN or separate launch mode.
