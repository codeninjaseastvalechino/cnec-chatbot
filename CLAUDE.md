# CNEC Chatbot — Claude Code Briefing

This file is read automatically by Claude Code on every session.
It contains everything needed to continue development without re-explaining context.

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

## Current Status

**Active milestone: Milestone 2 — MyStudio login + 2FA + full daily schedule**

| Milestone | Status |
|-----------|--------|
| 1 — LineLeader login + GBS/JR GBS tour pull + reschedule | ✅ Complete |
| 2 — MyStudio login + 2FA + full daily schedule | ⬜ Not started |
| 3 — Student lookup + camp details | ⬜ Not started |
| 4 — Move / create / cancel appointments | ⬜ Not started |
| 5 — Chat UI + scheduler + audit log + permissions | ⬜ Not started |
| 6 — Employee schedule generator (stretch goal) | ⬜ Not started |

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

---

## Project Structure

```
cnec-chatbot/
├── CLAUDE.md                        ← you are here
├── CNEC-Chatbot-Requirements.md     ← full requirements doc
├── run_milestone1.py                ← CLI entry point (run this)
├── requirements.txt
├── config/
│   └── settings.py                  ← ALL config lives here
├── core/
│   └── logger.py                    ← shared structured JSON logging
└── sites/
    └── lineleader/
        ├── auth.py                  ← login + Bearer token management
        └── schedules.py             ← API calls, session parsing, reschedule
```

Future milestones add:
- `sites/mystudio/` — MyStudio automation
- `sites/homebase/` — Homebase API (no browser needed)

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

## Python Version Warning

**The user is on Python 3.9.** Do NOT use:
- `str | None` → use `Optional[str]`
- `list[X]` → use `List[X]`
- `dict[str, X]` → use `Dict[str, X]`

Always import from `typing`: `from typing import Optional, List, Dict, Any, Union`

---

## Safety Rules (Non-Negotiable)

From requirements §8:
- **Never write to a live site without explicit user confirmation**
- Any function that modifies data must have a confirmation step before executing
- Ambiguous input → stop and ask, never assume
- Unexpected site state → halt, do not touch anything, report to user

---

## Config Philosophy

Everything center-specific lives in `config/settings.py` loaded from `.env`.
No hardcoded values in site modules. To deploy for another Code Ninjas center:
update `.env` and the org/center IDs in `settings.py` only.

---

## Credentials Strategy

| Site | Storage |
|------|---------|
| LineLeader (Site 2) | `.env` file |
| MyStudio (Site 1) | `.env` file |
| Microsoft Graph (2FA) | `.env` file |
| Homebase (Site 3) | Runtime prompt ONLY — never saved to disk |

Homebase credentials must never be stored. Owner enters them at runtime.
They are held in memory for the session only.

---

## Dependencies

```
playwright>=1.44.0    # browser automation (login only)
requests>=2.31.0      # direct API calls (data fetching)
python-dotenv>=1.0.0  # .env loading
openpyxl>=3.1.0       # Excel export (Milestone 2)
apscheduler>=3.10.0   # scheduled runs (Milestone 5)
rich>=13.7.0          # terminal output formatting
```

---

## How to Run

### Milestone 1 — GBS Tours + Reschedule
```bash
cd cnec-chatbot
source .venv/bin/activate
python3 run_milestone1.py
```

The CLI:
1. Logs in to LineLeader (headless by default, token cached ~1 hour)
2. Fetches today's Tours and displays a formatted table with child names/ages
3. Prompts: "Reschedule a tour? (y/n)"
4. If yes: enter by tour number (e.g. `1`) or name (e.g. `Journei`)
5. If ambiguous name match: shows 2–3 choices, ask to be more specific
6. Confirmation prompt before writing to the API

**Exit codes:**
- `0` — success
- `1` — missing .env credentials or API error
- `2` — login failure (check credentials, token cache may be stale)

---

## Development Commands

### Debug Mode — Watch the Playwright browser login
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

## Testing

**Current state:** No unit tests exist (Milestone 1 was spike-driven).

**When to add tests (Milestone 2+):**
- Before adding MyStudio or Homebase modules
- If a module has more than one public function
- For critical paths (login, reschedule with confirmation)

**Testing strategy (recommended):**
- Use `pytest` + `pytest-asyncio` (we have async login)
- Mock `requests` (API calls), not Playwright
- Test patterns: auth token caching, session parsing, name matching
- Avoid testing Playwright directly (too fragile, slow)

Example fixture:
```python
@pytest.fixture
def mock_api_response(monkeypatch):
    def _mock(endpoint, response_json):
        monkeypatch.setattr("requests.get", lambda *a, **k: Mock(json=lambda: response_json))
    return _mock
```

---

## Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | MyStudio API endpoints | 🔄 Needs live site inspection (Milestone 2) |
| 2 | Does MyStudio rate-limit Playwright? | 🔄 Test early |
| 3 | Homebase API write endpoints for schedule publishing | ✅ Confirmed working |
| 4 | LineLeader write endpoint for rescheduling Tours | ✅ Confirmed — `PUT /api/v3/tasks/{item_id}` |
| 5 | Child name lookup from family record | ✅ Confirmed — `GET /families/{id}` → `children[]` |
| 6 | GBS vs JR GBS distinction | ✅ Confirmed — description field + `custom_values JUNIOR` fallback |

---

## Users & Permissions

| Role | Access |
|------|--------|
| Owner + Wife | All tasks including employee schedule (Milestone 6) |
| Staff (1 person) | Tasks 1–5 only — employee schedule completely hidden |

Owner identity enforced at session start via PIN or separate launch mode.
