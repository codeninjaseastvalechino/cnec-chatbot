# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Project Is

An **AI Operations Assistant** for **Code Ninjas Eastvale Chino** — an AI agent
that accepts natural language instructions and executes scheduling, data retrieval,
and administrative tasks across three platforms. Not a chatbot, not scripted
automation: Claude reasons about intent, picks the right tool, and acts — with
staff confirmation before any write operation.

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
| **Setup** | `pip install -r requirements.txt` | One-time only (no Playwright needed) |
| **CLI (Milestone 1)** | `python3 run_milestone1.py` | Show/reschedule tours, real LineLeader data |
| **Web UI (mock)** | `TEST_MODE=true python3 app.py` | Zero API costs, instant feedback |
| **Web UI (real)** | `python3 app.py` | Uses Claude API + LineLeader data |
| **Chatbot CLI** | `python3 test_chatbot.py` | Debug chatbot engine without web UI |
| **Clear LineLeader token** | `rm -f browser_state/lineleader_token.json` | Force fresh LineLeader login |
| **Clear MyStudio cookies** | `rm -f browser_state/mystudio_cookies.json` | Force fresh MyStudio login + auto-OTP |
| **View logs** | `tail -f logs/cnec_chatbot.log \| jq .` | Stream structured JSON logs |
| **Set provider** | `LLM_PROVIDER=ollama python3 app.py` | Switch to Ollama backend |

---

## ⚠️ Common Gotchas

**These are not obvious — remember them:**

| Issue | Impact | Solution |
|-------|--------|----------|
| **Forgot `LLM_PROVIDER` env var** | App defaults to Claude, burns API credits silently | Always set `LLM_PROVIDER=claude` or use `TEST_MODE=true` for dev |
| **MyStudio OTP cookie expires silently** | Triggers re-login every 30 days | Auto-handled: app reads OTP from Gmail automatically (M8). No manual entry needed. |
| **LineLeader token cached for ~1 hour** | Stale data if run after hour-long pause | Safe: 5-min buffer auto re-logins before expiry. Manual: `rm browser_state/lineleader_token.json` |
| **Mock mode is instant, real mode is not** | Expectations mismatch during dev→prod switch | Mock mode: <10ms responses. Claude mode: ~500-800ms per query |
| **LineLeader login uses PKCE** | If login hangs, clear the token cache | Run: `rm -f browser_state/lineleader_token.json` (no browser needed) |
| **Python 3.9 type hints** | Import errors on newer syntax | Always use `Optional[str]` not `str \| None`, `List[X]` not `list[X]` |

---

## Table of Contents

**Core Reference:**
- [Current Status](#current-status)
- [Common Gotchas](#-common-gotchas)
- [How to Run](#how-to-run)
- [Testing](#testing)
- [Development Commands](#development-commands)
- [Debugging & Troubleshooting](#debugging--troubleshooting)

**Architecture & Reference:**
- [Project Structure](#project-structure)
- [Multi-Provider LLM Architecture](#multi-provider-llm-architecture)
- [Environment Variables](#environment-variables)
- [Dependencies & Setup](#dependencies--setup)
- [Claude API Models & Pricing](#claude-api-models--pricing)
- [Safety & Design](#safety--design)
- [Architecture Decision Log](#architecture-decision-log)
- [Site 2 (LineLeader) Deep Dive](#site-2--lineleader-childcarecrm-architecture-milestone-1) — detailed reference
- [Site 1 (MyStudio) API Reference](#site-1--mystudio-api-reference-milestone-2) — detailed reference
- [Known Issues & Tracking](#known-issues--tracking)
- [Users & Permissions](#users--permissions)

---

## Current Status

**Last updated: 2026-06-25**

| Milestone | Status | Notes |
|-----------|--------|-------|
| 1 — LineLeader login + GBS/JR GBS tour pull + reschedule | ✅ Complete | Production-ready CLI tool |
| 2 — MyStudio login + unified schedule + chat/Excel output | ✅ Complete | Direct API + OTP 2FA, 30-day cookie caching |
| 3 — Student lookup | ✅ Complete | See session notes below |
| 3b — Camp details | ✅ Complete | Camp list, enrollment counts, kid names + ages, unique kid dedup, week-of-date resolution |
| 3c — Camp revenue analysis | ✅ Complete | Per-camp revenue via N+1 getParticipantRegDetails; flags comps, discounts, renames, family patterns |
| 4 — Move / cancel appointments (single session) | ✅ Complete | Recurring all-future ops have gaps — see Known Issues |
| 4 — Move / cancel appointments (all-future recurring) | ⚠️ Partial | API returns Success but does not cascade — under investigation |
| 4 — Book new appointment | ⬜ Not started | Blocked: requires student-session token not yet solved |
| 5 — Chat UI + Claude API + function calling + Excel export | ✅ Complete | Web UI + multi-provider LLM (Claude/Ollama) |
| 6 — Employee schedule generator (stretch goal) | ⬜ Not started | Backlog |
| 7 — Railway deployment (public launch) | ✅ Complete | Live at cnec.up.railway.app; TZ=America/Los_Angeles required for correct timezone filtering |
| 8 — Auto Gmail OTP extraction | ✅ Complete | Gmail IMAP + app password; auto-extracts code, no human in the loop |
| 9 — Features & roadmap panel in UI | ⏳ Deferred | Waiting on app revamp — see planning notes below |

### Milestone 9 — Features & roadmap panel (deferred — pending app revamp)

**Goal:** Show users what they can do right now and what is coming, directly inside the app UI — so they don't request features already in the pipeline.

**Why deferred:** The app UI is being revamped. Implementing M9 before the revamp risks duplicate or conflicting work. Resume this milestone once the new UI structure is settled.

**Planned scope (agreed 2026-06-14):**

- A "What can I ask?" section visible in the UI (sidebar section or help modal — TBD based on new UI layout)
- Three tiers of content:
  - **Live now** — features users can use immediately, each with example queries
  - **Coming soon** — in-progress or planned features (sets expectations, reduces redundant requests)
  - **Known gaps** — partial features (all-future recurring ops, book new appointment) with a plain-English note on why they're limited — staff-facing only, or omit from public view
- Content derived from the feature inventory below; keep in sync with milestone status table above

**Feature inventory for panel content (as of 2026-06-14):**

| Feature | Status | Example queries |
|---------|--------|-----------------|
| Full daily schedule (LineLeader + MyStudio merged) | Live | "Show me today's full schedule", "What's on Friday?" |
| GBS & JR GBS tours with child names, ages, staff | Live | "Any GBS tours tomorrow?", "List upcoming tours this week" |
| Reschedule a tour | Live | "Reschedule the 3pm tour to 4:30", "Move Wittie Hughes to Thursday at 5" |
| Student lookup by name | Live | "Look up Veshant Bhatia", "What sessions does Alex have coming up?" |
| Cancel a student session (single) | Live | "Cancel Alex's session on June 20" |
| Move a student session (single) | Live | "Move Alex's June 18 class to June 20 at 3pm" |
| Excel export of any schedule | Live | "Download today's schedule as Excel", "Export Friday's tours" |
| Cancel / move all-future recurring sessions | Partial — API gap | Returns success but only affects the targeted occurrence; root cause under investigation |
| Book a new appointment | Blocked | Requires POS-flow student token not obtainable via staff login |
| Camp enrollment details + roster | Live | "Show me next week's camps", "Who's in the Minecraft camp?" |
| Camp revenue analysis | Live | "How much revenue will next week's camp generate?", "What did the Robotics camp bring in?" |
| Employee schedule (Homebase) | Coming (M6) | Homebase integration not yet started |
| Quick-query shortcuts bypassing Claude | Coming | Sidebar buttons currently still go through Claude; true bypass planned |

**Implementation notes (for when work resumes):**
- Do NOT implement until the app revamp layout is finalized — placement (sidebar vs. modal) depends on the new structure
- Keep the feature list in the panel driven from a data structure, not hardcoded strings, so it stays in sync as milestones complete
- "Partial" and "blocked" items: show to staff (they manage expectations); consider hiding from any future customer-facing view
- No new Python modules needed — this is purely a frontend/template change to `app.py`

---

### Session 2026-06-25 — Milestone 3c (camp revenue analysis)

**Changes made:**
- ✅ **`config/settings.py`** — added `CAMP_HALF_DAY_PRICE = 249.00` and `CAMP_FULL_DAY_PRICE = 399.00`
- ✅ **`sites/mystudio/camps.py`** — new revenue functions:
  - `_expected_camp_price(title)` — infers standard price from title: "FULL DAY"/"ALL DAY" → $399, otherwise → $249
  - `_get_roster_raw_rows(event_id, parent_id)` — same 36-column getFilterDetails call as `get_camp_roster`, but returns raw row dicts (needed to check for `participant_id`/`student_id` fields)
  - `get_camp_revenue(camp)` — N+1 pattern: roster rows → per-kid `getParticipantRegDetails` → finds `event_details` entry matching `event_id` with `payment_status_label == "Active"` → sums `paid_amount`. Detects: comped ($0), discounted (< standard), cancelled (excluded), family patterns (same buyer, multiple kids), camp renames (same date, different event_id). Returns structured dict with `total`, `enrolled`, `expected_price`, `kids`.
  - `format_camp_revenue(result)` — formats single camp with total, gotcha sections (renames, comps, discounts, cancellations, families), and full per-kid enrollment list with flags
  - `format_week_revenue(results)` — one-line-per-camp summary across a week
- ✅ **`chatbot.py`** — `get_camp_revenue` tool:
  - Loading message: `"Calculating camp revenue — fetching payment details per kid..."`
  - Parameters: `week_of_date_str` (raw week phrase), `camp_name` (keyword filter)
  - Default: if no week given, uses next calendar week
  - Cap: refuses to compute >8 camps at once (asks user to narrow)
  - Handler: `_handle_get_camp_revenue()`
- ✅ **`tests/sites/mystudio/test_camps.py`** — tests for `_expected_camp_price`, `format_camp_revenue`, `format_week_revenue`, rename detection

**Key discoveries:**
- `getFilterDetails` roster rows do NOT include `participant_id`/`student_id` in the 36-column format — fall back to `find_student_by_name` + buyer name match for ID resolution
- `participant_id` is the correct unique key per child (siblings share `student_id`)
- `payment_status_label == "Active"` filter is required — cancelled entries still carry a `paid_amount` value
- Camp rename scenario: parent paid $399 in April for "Robotics Engineering (Ages 8+)", camp renamed in May to "ALL DAY CAMP: Robotics Engineering + Cybersecurity Coding". Kid migrated to new `event_id` at $0; real payment lives on old `event_id`. Fix: when exact `event_id` shows $0 + Active, look for another Active entry on the **same start_date** with `paid_amount > 0` → use that amount and flag as `renamed_from`.
- `start_date` format in `event_details` is "Jun 22, 2026" (matches `camp.start_dt.strftime("%b %-d, %Y")`)

**Revenue gotcha callout logic (in order):**
1. **Camp renames** — $0 on current event_id but matching same-date paid entry found → revenue recovered, callout shows original event title
2. **Comped ($0)** — Active entry with $0 and no rename found → flagged with parent name
3. **Discounted** — Active entry with 0 < paid < expected → flagged with actual vs standard price
4. **Cancelled** — entry with `payment_status_label == "Cancelled"` → excluded from total, listed separately
5. **Family pattern** — same `buyer_name` appears for 2+ enrolled kids → grouped with amounts

**Pricing logic:**
- Title contains "FULL DAY" or "ALL DAY" → $399 (`CAMP_FULL_DAY_PRICE`)
- Anything else (AM CAMP, PM CAMP, half-day) → $249 (`CAMP_HALF_DAY_PRICE`)
- Both JR and regular camps follow the same pricing

---

### Session 2026-06-23 — Billing cycle intelligence for lookup_student

**Changes made:**
- ✅ **`sites/mystudio/students.py`** — new `get_membership_reg_details()`:
  - `POST /v43/Api/PortalApi/membersRegDetails` with `selected_membership_id = reg_id`
  - Returns `membership_title` (e.g. "CREATE: Plus (2x/Week)"), `reg_no_of_classes` (sessions/week), `reg_attendance_period` ("CPW"), `preceding_payment_date` (cycle start, YYYY-MM-DD), `next_payment_date` (cycle end, YYYY-MM-DD)
  - `reg_id` comes from `getParticipantRegDetails → participant_details.reg_id` — no extra search needed
- ✅ **`chatbot.py`** — `_handle_lookup_student` upgraded:
  - Surfaces `membership_title` (program name) in output
  - Uses `act_att` from `membership_details` for attended count (was manually counting raw session rows — incorrect)
  - Computes `expected_this_cycle = floor(cycle_days / 7 × reg_no_of_classes)` from real plan data
  - Computes `remaining = expected - attended` and shows it explicitly
  - Uses `preceding_payment_date` directly for cycle start (was doing month-subtraction math — buggy)
  - Annotates upcoming sessions that fall after `cycle_end` with `[next billing cycle]`
  - Updated tool description: "this month" and "billing cycle" treated as equivalent — Claude answers directly without follow-up
- ✅ **`tests/sites/mystudio/test_students.py`** — 4 new tests for `get_membership_reg_details`

**Key discoveries:**
- `act_att` in `membership_details` = attended sessions this billing cycle (not total ever) — matches `attendance_last_30_days` when cycle ≈ 30 days
- `remaining_no_of_classes` in `membersRegDetails` is always "0" for monthly recurring plans — not useful
- `next_payment_date` format differs between endpoints: `getParticipantRegDetails` returns "Jun 27, 2026" but `membersRegDetails` returns "2026-06-27" (ISO)
- MyStudio schedules recurring sessions past billing cycle boundaries — a session on Jun 29 appears in the current cycle's upcoming list even though the cycle ends Jun 27; annotating with `[next billing cycle]` lets Claude present this correctly

**Billing cycle math:**
```
cycle_start  = preceding_payment_date  (e.g. 2026-05-27)
cycle_end    = next_payment_date        (e.g. 2026-06-27)
weeks        = (cycle_end - cycle_start).days / 7
expected     = floor(weeks × reg_no_of_classes)
remaining    = expected - act_att
```

---

### Session 2026-06-14 — Milestone 3b (camp details)

**Changes made:**
- ✅ **`sites/mystudio/camps.py`** — new module:
  - `CampRecord` dataclass — event_id, parent_id, title, start/end datetime, enrolled, capacity, event_show_status, age
  - `CampKid` dataclass — participant_name, buyer_name, phone, email, status, event_title, age (p_age from API)
  - `get_live_parent_events()` — dynamic parent group discovery, no hardcoded IDs
  - `get_camps_under_parent()` — filters null-date templates and camps with no real schedule
  - `get_all_upcoming_camps()` — two-step discovery, filtered + sorted by start_dt
  - `get_camp_roster()` — POST getFilterDetails with 36-column DataTables format, returns kid names + ages
  - `format_camps_summary()` — grouped by week, shows enrollment/capacity/spots left, filters hidden camps
  - `format_camp_roster()` — per-camp kid list, None-safe
- ✅ **`chatbot.py`** — `get_camp_details` tool:
  - `week_of_date_str` param — resolves to Monday of containing week (handles mid-week dates like "July 17")
  - `after_date_str` param — open-ended "from date" filter
  - `camp_name` param — fuzzy keyword filter
  - `include_roster` param — fetches kid names + ages per camp
- ✅ **`sites/mystudio/auth.py`** — three header fixes required for getFilterDetails:
  - Removed session-level `Content-Type: application/json` (was overriding form POST encoding)
  - Added `X-Requested-With: XMLHttpRequest` (PHP backend requires this for AJAX endpoints)
  - Inject `c_u_id_{user_id}` email cookie after OTP login (WebPortal sets this; API login doesn't)
- ✅ **`tests/sites/mystudio/test_camps.py`** — 31 unit tests (week_label, time_range, spots_left, filtering, formatting)

**Key discoveries:**
- `getFilterDetails` requires `filter_options` (with `s`), not `filter_option` — different from all other endpoints
- `filter_options` needs `child_event_type: "S"` (not `"AP"`) and parent ID in `all_event_id`
- 36 DataTables columns required (not 13 like class roster) — exact column layout captured from browser DevTools
- Hidden camps (`event_show_status="N"`) have real dates and appear in raw fetch — must filter in `format_camps_summary`
- `week_of_date_str` needed because "week of July 17" (Thursday) should return July 13–17, not July 17+
- `c_u_id_9901` email cookie + `X-Requested-With` were the two missing pieces that caused "User doesn't exist" error on all previous attempts

**auth.py header change safety:** `schedules.py`, `students.py`, and `write.py` all set their own per-request Content-Type — they are unaffected by the session-level change.

### Session 2026-06-05 — Milestone 3 + 4 (student lookup + write ops)

**Changes made:**
- ✅ **`sites/mystudio/students.py`** — new shared foundation module:
  - `StudentRecord` dataclass (`student_id`, `participant_id`, `name`, `belt_rank`, `parent_name`, `phone`)
  - `find_student_by_name()` — DataTables search via `POST /getstudent`, deduplicates by `participant_id`
  - `get_student_details()` — full profile via `GET /getParticipantRegDetails` (parent name, phone, rank, attendance counts)
  - `get_student_sessions_by_type()` — `GET /getParticipantRegDetailsByType` with `show_more_type=A` (returns all sessions, not just first 4)
  - `get_student_attendance_this_week()` — counts Attended sessions in current Mon–Sun week
  - `get_student_upcoming_appointments()` — returns `List[StudentAppointment]` with M4 fields populated
  - `get_available_slots()` — returns available class slots for a date (capacity > registered)
- ✅ **`sites/mystudio/appointments.py`** — added 3 optional fields: `registration_detail_id`, `class_appointment_times_id`, `class_appointment_id` (needed for cancel/move; backward compatible)
- ✅ **`sites/mystudio/write.py`** — new write module:
  - `cancel_student_appointment()` — `POST /v43/Api/PortalApi/removeParticipant`; `cancel_registration_type: "N"` (single) or `"Y"` (all-future)
  - `move_student_appointment()` — `POST /Api/v2/RescheduleCurrentAppointment`; `selected_reschedule_type + allow_recurring_reschedule: "N"` (single) or `"Y"` (all-future)
- ✅ **`config/settings.py`** — added `MYSTUDIO_API_V2_URL = "https://cn.mystudio.io/Api/v2"`
- ✅ **`chatbot.py`** — new tools and helpers:
  - `lookup_student` tool — find student by name, returns attendance + upcoming 30-day schedule
  - `cancel_student_session` tool — cancel single or all-future with `confirmed` dry-run pattern
  - `move_student_session` tool — move single or all-future with `confirmed` dry-run pattern
  - `_resolve_student()` helper — shared duplicate resolution: fetches active memberships for each match, auto-selects if only one has active programs, disambiguates with parent + program names if multiple
  - `_otp_prompt()` helper — deduplicates OTP message across all handlers
- ✅ **`test_mystudio.py`** — direct API test script (no Claude, no cost) for all 6 test cases
- ✅ **Unit tests** — 133 tests, all passing:
  - `tests/sites/mystudio/test_students.py` — 18 tests (search, attendance, parsing, sort)
  - `tests/sites/mystudio/test_write.py` — 17 tests (cancel/move success, flags, 401, network errors)

**Key discoveries during testing:**
- `getstudent` endpoint: `buyer_name` field = participant (child) name, NOT parent name — confusing but confirmed
- `getParticipantRegDetailsByType` with `show_more_type=S` silently returns only 4 sessions; use `show_more_type=A` for all
- Two accounts exist named "Veshant Bhatia" — same parent, same DOB; one has active memberships, one is inactive. `_resolve_student()` handles this automatically
- Searching for a parent name (e.g. "Venay Bhatia") returns 0 results — `getstudent` searches participant names only

**Known gaps (under investigation):**
- ⚠️ **All-future cancel**: `cancel_registration_type: "Y"` returns Success but recurring series is NOT deleted — only the targeted occurrence is removed. Single cancel (`"N"`) works correctly.
- ⚠️ **All-future reschedule**: `allow_recurring_reschedule: "Y"` returns Success but future occurrences are NOT moved. Single reschedule (`"N"`) works correctly.
- Both gaps need DevTools capture of what the browser actually sends for recurring operations — there may be additional parameters required.
- ⬜ **Book new appointment**: `stripeClassAppointmentRegistration` requires a student-session `token` from the POS flow — not obtainable from staff auth session. Deferred.
- ⚠️ **"Monday" resolves to nearest Monday from today**, not from the from-date context. E.g. moving "from June 13 to Monday" resolves Monday as June 8 (past relative to June 13). Fix: after resolving to_date, if it falls before from_date, roll forward 7 days.

### Session 2026-06-04 — Tool pattern, date safety, unit tests

**Changes made:**
- ✅ **Tool pattern enforced** (ADR-009) — all tools pass raw date phrases from Claude; Python owns resolution, validation, and conflict detection. Claude never does date math.
- ✅ **`core/date_utils.py`** — new shared module: `resolve_date()`, `resolve_time()`, `resolve_datetime()`. Handles day names, month+day, ordinals ("8th", "the 11th"), relative words, and day/date conflict detection ("Friday June 6th" → caught).
- ✅ **`ChatbotEngine._resolve_tool_date()`** — shared helper on the class; all handlers call it instead of duplicating resolve logic.
- ✅ **`get_upcoming_gbs_tours` tool** — new tool replacing Claude's fan-out across multiple dates. Single `/action-items?future` call, filtered by `after_date`, deduplicated, capped at `limit`. "After June 16th" is exclusive (returns from June 17th).
- ✅ **Multi-tool fix** (ADR-010) — `llm_provider.py` now collects ALL `tool_use` blocks per response (not just the first). Agentic loop executes all in one batch and returns all results in one user message. Fixes 400 errors when Claude fires parallel tool calls.
- ✅ **Schedule header fixed** — `format_unified_schedule` now uses the actual requested date in its header ("Schedule for Friday, June 5, 2026") so Claude copies it rather than computing its own.
- ✅ **`_parse_single_item` bug fixed** — `display_type` was referenced before being extracted from the item dict (would NameError if called).
- ✅ **Unit tests** — 92 tests across 5 files, all passing:
  - `tests/core/test_date_utils.py` — resolve_date, resolve_time, conflict detection, ordinals
  - `tests/sites/lineleader/test_schedules.py` — _calculate_age, _is_junior, _build_put_payload, _parse_tasks, _parse_single_item, get_upcoming_gbs_tours
  - `tests/sites/mystudio/test_schedules.py` — _parse_student_to_appointment
  - `tests/test_chatbot_helpers.py` — _resolve_tool_date
  - `tests/test_llm_provider.py` — multi-tool extraction
- ✅ **`pytest` added** to `requirements.txt`

**Run tests:** `python3 -m pytest tests/ -v`

### Session 2026-06-03 — Cloud prep + observability

**Changes made:**
- ✅ **Playwright removed** — LineLeader login is now pure `requests` OAuth2 PKCE flow (ADR-007). No browser, no Chromium install. Cloud-deployable.
- ✅ **Richer chatbot logging** — each query now logs: user query text, tool name + inputs, tool duration, total request duration, response size
- ✅ **MyStudio schedule logging** — logs non-empty slot count and total roster-fetch time
- ✅ **`analytics.py`** — new query analytics module writing to `logs/query_analytics.jsonl`:
  - `top_intents()` — groups by tool + date bucket (today/tomorrow/future/past) — immune to spelling/phrasing variants
  - `top_tools()` — raw tool call frequency
  - `top_queries()` — raw query text (useful for UX copy decisions)
  - `recent()` — last N entries
- ✅ **`GET /api/analytics`** — new endpoint exposing all analytics data as JSON
- ✅ **Quick-query path designed** — `query_type` field in analytics log supports "natural_language" vs "quick_query" for future shortcut buttons that bypass Claude

### Milestone 2 — Complete (2026-06-02)

**What's built:**
- ✅ MyStudio login + OTP 2FA (direct API, no Playwright)
- ✅ 30-day cookie caching — one OTP login per month
- ✅ Class schedule fetching (`getClassScheduledetails` + `getClassdatatabledetails`)
- ✅ Student roster parsing with parent names, ranks, phone numbers
- ✅ LineLeader switched to `/tasks` endpoint — includes ALL tours
- ✅ Unified time-ordered schedule (LineLeader + MyStudio merged)
- ✅ Chat UI + Excel export (Time | Student | Type | Belt | Parent)
- ✅ Mock chatbot with realistic MyStudio data
- ✅ OTP flow surfaced in chat UI — user enters code in browser, not terminal

**MyStudio 2FA flow (by design, not a workaround):**
- Cookies expire every 30 days
- When expired, chatbot responds in the browser: *"🔐 MyStudio verification needed. An OTP code was sent to eastvalechinocodeninjas@gmail.com. Please reply with the 6-digit code."*
- User enters code in chat → cookies cached for 30 more days
- No terminal access needed — fully browser-based
- Implementation: `MystudioOTPRequired` exception in `auth.py`, caught in `chatbot.py`

**Key architectural decision:** MyStudio uses session-based auth (PHP cookies), NOT bearer tokens. Session persists 30 days with `remember_me: true`.

**Files created/updated:**
- `sites/mystudio/auth.py` — Cookie-based session auth
- `sites/mystudio/schedules.py` — Real confirmed endpoints
- `sites/mystudio/appointments.py` — StudentAppointment data structures
- `config/settings.py` — MyStudio URLs + IDs (company_id=578, user_id=9901)
- `format_tours.py` — Unified schedule formatter

**For detailed MyStudio API specs, credentials, and implementation notes:** See [Site 1 (MyStudio) API Reference](#site-1--mystudio-api-reference-milestone-2) at the end of this document.

**Backlog:**
- ⬜ Filter appointments by class type (fuzzy mapping: "create" → "CREATE (CODING)")

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
- `app.py` — Flask web server on port 5001
  - Routes: GET `/`, POST `/api/chat`, GET `/api/audit-log`, GET `/api/export/tours`, GET `/api/analytics`
  - Instantiates provider based on `LLM_PROVIDER` env var (defaults to Claude)
- `chatbot.py` — ChatbotEngine class (provider-agnostic) with agentic loop and tools:
  - `get_full_schedule` — unified LineLeader + MyStudio schedule for any date
  - `get_gbs_tours` — GBS tours only (LineLeader) for a specific date
  - `get_upcoming_gbs_tours` — next N GBS tours from a given date forward (replaces multi-date fan-out)
  - `reschedule_tour` — reschedule a tour to new time
  - All tools accept raw date phrases; Python resolves via `core/date_utils.py`
  - `_resolve_tool_date()` — shared date resolution helper on the class
  - Logs: user query, tool name + inputs, tool duration, total request time
  - Writes one entry per query to `logs/query_analytics.jsonl`
- `analytics.py` — Query analytics: `top_intents()`, `top_tools()`, `top_queries()`, `recent()`
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
├── analytics.py                     ← Query analytics (top_intents, top_tools, recent)
├── requirements.txt
├── config/
│   └── settings.py                  ← ALL config lives here
├── core/
│   ├── logger.py                    ← shared structured JSON logging
│   └── date_utils.py                ← date/time resolution (resolve_date, resolve_time, resolve_datetime)
├── sites/
│   ├── lineleader/
│   │   ├── auth.py                  ← Playwright-free OAuth2 PKCE login (pure requests)
│   │   └── schedules.py             ← ChildCareCRM API calls, parsing, reschedule
│   └── mystudio/
│       ├── auth.py                  ← Cookie-based session auth + OTP 2FA
│       ├── schedules.py             ← Class schedule + student roster fetching
│       ├── appointments.py          ← StudentAppointment data structure
│       ├── students.py              ← Student lookup, sessions, attendance
│       ├── write.py                 ← Cancel / move appointments
│       └── camps.py                 ← Camp list, roster, formatting (M3b)
├── asset/
│   └── cnec-logo.jpeg               ← Code Ninjas Eastvale Chino logo
├── logs/
│   ├── cnec_chatbot.log             ← structured JSON logs (operations)
│   ├── audit.jsonl                  ← audit trail: every user message + response
│   └── query_analytics.jsonl        ← query analytics: tool calls, timing, intents
├── exports/                         ← Excel files saved here
├── tests/
│   ├── core/
│   │   └── test_date_utils.py       ← resolve_date, resolve_time, conflict detection, ordinals
│   ├── sites/
│   │   ├── lineleader/
│   │   │   └── test_schedules.py    ← _build_put_payload, _parse_tasks, get_upcoming_gbs_tours, etc.
│   │   └── mystudio/
│   │       ├── test_schedules.py    ← _parse_student_to_appointment
│   │       ├── test_students.py     ← student lookup, attendance, parsing
│   │       ├── test_write.py        ← cancel/move success, flags, errors
│   │       └── test_camps.py        ← CampRecord helpers, filtering, formatting
│   ├── test_chatbot_helpers.py      ← _resolve_tool_date
│   └── test_llm_provider.py         ← multi-tool extraction
└── browser_state/
    ├── lineleader_token.json        ← cached Bearer token + expiry (~1 hour)
    └── mystudio_cookies.json        ← cached session cookies (30-day expiry)
```

**Run tests:** `python3 -m pytest tests/ -v`

Future milestones add:
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

### ADR-001 — Playwright for browser automation (superseded)
**Date:** May 2026 | **Milestone:** 1 | **Superseded by ADR-007**

**Original decision:** Use Playwright for login — OAuth2 PKCE flow was believed
to require a real browser for CSRF tokens and code challenge handling.

**Superseded:** ADR-007 replaced this with pure requests.

---

### ADR-002 — Original plan: Playwright interception for all data fetching
**Date:** May 2026 | **Milestone:** 1

**Decision (original):** Navigate to schedule pages and intercept internal
XHR/fetch API calls to capture JSON responses.

**Superseded by ADR-003.**

---

### ADR-003 — Hybrid: Playwright login → direct requests for all API calls
**Date:** May 2026 | **Milestone:** 1 | **Superseded by ADR-007**

**Decision:** Use Playwright ONLY for login. Extract Bearer JWT from the
`/api/v3/sso/login` response. Use Python `requests` for all subsequent API calls.

**Superseded:** Login no longer requires Playwright. See ADR-007.

**Token lifecycle (still applies):**
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

### ADR-007 — Playwright-free LineLeader login (pure requests OAuth2 PKCE)
**Date:** June 2026 | **Milestone:** 1 (cloud deployment prep)

**Decision:** Replace Playwright login with a pure `requests` OAuth2 PKCE flow.
Removes Chromium dependency entirely — app is now deployable to any standard
Python cloud host.

**How it works (4 steps, all pure requests):**
1. GET `https://login.lineleader.com/authorize?client_id=enroll&...` → sets PHPSESSID
2. GET `https://login.lineleader.com/login?from=enroll` → extract `_csrf_token` from server-rendered HTML hidden field
3. POST credentials (`_csrf_token`, `_username`, `_password`) → 302 redirect chain → callback URL `https://my.childcarecrm.com/#/code?code=...`
4. POST `https://live.childcarecrm.com/api/v3/sso/login` with `{code, code_verifier}` → Bearer JWT

**Key discoveries:**
- `login.lineleader.com` is PHP/Symfony — login page HTML contains a server-rendered CSRF token hidden field
- `client_id` is `"enroll"`, redirect URI is `https://my.childcarecrm.com/#/code`
- Token exchange endpoint is `POST /api/v3/sso/login` with `{code, code_verifier}`
- The PKCE math (SHA256 + base64url) is standard and trivial in Python

**Why Playwright was originally kept:** The original note said "Cannot be replicated with raw requests reliably" — this was overly conservative. The CSRF token is server-rendered in HTML, not JS-generated.

**Impact:** `playwright` removed from `requirements.txt`. No `playwright install chromium` step needed.

---

### ADR-008 — Agent refactor: registry pattern + clean system prompt
**Date:** June 2026 | **Milestone:** 5 (completed)

**Decision:** Refactored `chatbot.py` to use a tool registry pattern.
- System prompt reduced to identity + safety rules + tone only
- All routing rules and format templates removed from the prompt
- Tool descriptions rewritten to describe data returned, not routing logic
- Format instructions moved into Python tool handlers
- `_register()` / `_execute_tool()` replace the if/elif dispatch chain
- All handler signatures normalized to `(self, tool_input: dict)`

**Why:** As Milestones 3–6 add more tools, the old pattern would have
accumulated routing rules in the system prompt — a maintenance trap.
The registry means adding a new tool is one `_register()` call + one handler.
The system prompt never changes.

---

### ADR-009 — Claude passes raw phrases; Python owns all date resolution
**Date:** June 2026 | **Milestone:** 5

**The pattern in one sentence:**
Claude reads intent → picks a tool → Python executes it → Python formats the result → Claude frames it.

**Decision:** All tool parameters that involve dates or times are passed as raw natural language phrases exactly as the user said them. Python resolves, validates, and detects conflicts. Claude never does date math.

**What this means in practice:**
- Tool schemas use `date_str`, `time_str`, `after_date_str` — described as "pass the raw phrase, do not resolve"
- `core/date_utils.py` owns all resolution: day names, month+day, ordinals ("8th"), relative words, day/date conflict detection
- `ChatbotEngine._resolve_tool_date()` is the shared entry point for all handlers
- If Claude says "Friday June 6th" and June 6 is a Saturday, Python catches it and returns the conflict message — Claude never writes to the API

**Why:** Claude's date arithmetic is unreliable (confirmed: "Friday" → June 6 when Friday is June 5). A wrong date on a read tool means a wrong schedule. A wrong date on a write tool (reschedule) means corrupted data. Python is deterministic; Claude is not.

**Boundaries:**
- Claude's job: extract what the user literally said ("Friday June 6th", "10am")
- Python's job: resolve to datetime, validate, convert to UTC, call the API

---

### ADR-010 — Multi-tool batch execution in agentic loop
**Date:** June 2026 | **Milestone:** 5

**Decision:** `llm_provider.py` collects ALL `tool_use` blocks from a single Claude response (not just the first). The agentic loop in `chatbot.py` executes all tools in the batch sequentially and returns all results in one user message.

**Why:** The Anthropic API requires every `tool_use` block to have a matching `tool_result` in the immediately following user message. The original code extracted only the first tool_use block, silently dropping the rest, causing orphaned IDs and 400 errors on the next API call when Claude sent multiple tool calls in one response.

**Impact:** Claude can now make parallel tool calls (e.g. fetch two dates at once). Tools execute sequentially in Python — no true parallelism yet, but correctness is restored.

**Note:** Parallel tool calls are a symptom of a missing tool (e.g. `get_upcoming_gbs_tours` was added to eliminate the multi-date fan-out pattern). When Claude fans out, it's a signal to add a more appropriate tool.

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

# 4. Create .env from template
cp .env.example .env
# Edit .env and fill in LINELEADER_USERNAME, LINELEADER_PASSWORD, etc.
```

> **No Playwright install needed.** LineLeader login uses a pure requests OAuth2
> PKCE flow — no browser required (ADR-007).

### Dependency Versions

Listed in `requirements.txt` with version constraints (>=). Pinned versions only if stability issues arise.

```
requests>=2.31.0      # all HTTP calls — LineLeader login + API, MyStudio API
python-dotenv>=1.0.0  # .env loading
anthropic>=0.25.0     # Claude API (Milestone 5 web UI)
flask>=3.0.0          # web server (Milestone 5)
openpyxl>=3.1.0       # Excel export (Milestone 5)
apscheduler>=3.10.0   # scheduled runs (Milestone 6 — future)
rich>=13.7.0          # terminal output formatting
openai>=1.0.0         # OpenAI SDK (Ollama compatibility)
# NOTE: playwright removed (ADR-007) — login is pure requests OAuth2 PKCE
```

### Dependency Management

**Updating dependencies:**
```bash
# Update all dependencies to latest compatible versions
pip install --upgrade -r requirements.txt

# Update a specific package
pip install --upgrade anthropic
```

### First-Time Setup Checklist

Before running any milestone, verify this checklist:

- [ ] Python 3.9 confirmed: `python3 --version`
- [ ] Virtual environment created and activated: `source .venv/bin/activate`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] `.env` file created from `.env.example`
- [ ] Required credentials filled in: `LINELEADER_USERNAME`, `LINELEADER_PASSWORD`, `ANTHROPIC_API_KEY` (for Claude mode)
- [ ] Token cache cleared (fresh login): `rm -f browser_state/*.json`
- [ ] Quick test: `TEST_MODE=true python3 app.py` succeeds and web UI loads at `http://localhost:5001`

If any step fails, check [Debugging & Troubleshooting](#debugging--troubleshooting) → [Login Fails](#login-fails).

---

## How to Run

### Prerequisite: Setup
Before running any milestone, complete "Dependencies & Setup" above (one-time).

Verify setup:
```bash
source .venv/bin/activate
python3 -c "import requests; import anthropic; import flask; print('✅ Setup OK')"
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

### Debug Mode — Trace the LineLeader Login
Login is pure `requests` (no browser). To trace what's happening:

```bash
# Watch the auth log in real time
tail -f logs/cnec_chatbot.log | jq 'select(.module == "sites.lineleader.auth")'

# Or add a one-off print to auth.py _follow_to_callback() to dump each redirect URL
```

Useful for diagnosing CSRF token extraction failures or redirect chain changes.

---

## Debugging & Troubleshooting

### Login Fails
**Symptom:** Exit code 2, or "Invalid credentials" error.

**Debug steps:**
1. Verify `.env` has correct `LINELEADER_USERNAME` and `LINELEADER_PASSWORD`
2. Check credentials manually in a browser at `https://my.childcarecrm.com`
3. Clear token cache: `rm -f browser_state/lineleader_token.json`
4. Check `logs/cnec_chatbot.log` for `"level": "ERROR"` entries in `sites.lineleader.auth`

**Common issues:**
- Password changed — update `.env` and clear token cache
- Account locked after failed attempts — wait 5 min, try again
- CSRF token extraction fails — login page HTML may have changed; check `_csrf_token` field name in the form

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

**Testing matrix — choose based on your goal:**

| Scenario | Command | Cost | Speed | Best For |
|----------|---------|------|-------|----------|
| **Rapid UI iteration** | `TEST_MODE=true python3 app.py` | Free | Instant | UI debugging, no API calls |
| **CLI tool (real data)** | `python3 run_milestone1.py` | Free | ~2-5 sec | Tour reschedule workflow |
| **Chatbot engine only** | `python3 test_chatbot.py` | Free (mock) or $0.001-0.005 (Claude) | <1 sec (mock), ~500ms (Claude) | Tool calling & Claude integration |
| **Full integration** | `python3 app.py` | $0.001-0.005/query | <1 sec | Pre-production validation |

### Testing Approaches

**Current status:** Manual testing only. Unit tests (pytest) planned for Milestone 3+ (MyStudio/Homebase modules).

#### 1. Web UI — Mock Mode (Fastest, Zero Cost)
```bash
TEST_MODE=true python3 app.py
```
- Starts Flask on `http://localhost:5001`
- Instant mock responses (no API calls)
- Perfect for UI iteration and debugging
- No credentials needed

#### 2. CLI Tool — Real LineLeader Data
```bash
python3 run_milestone1.py
```
- Tests login flow, API calls, reschedule workflow
- Shows live data from LineLeader
- Requires `.env` credentials
- Exit code indicates success/failure

#### 3. Chatbot Engine CLI — Direct Testing
```bash
python3 test_chatbot.py
```
- Interactive chat with ChatbotEngine or MockChatbotEngine
- Type queries, see Claude tool responses
- No web UI overhead
- Best for debugging tool integration

#### 4. Full Integration — Real Claude + Real Data
```bash
python3 app.py
```
- Real Claude API + real LineLeader/MyStudio data
- Requires `ANTHROPIC_API_KEY` in `.env`
- Cost: ~$0.001-0.005 per query
- Best for final validation before deployment

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

## Known Issues & Tracking

### ✅ Confirmed & Resolved
| Question | Answer |
|----------|--------|
| MyStudio API endpoints | Confirmed — session-based auth with OTP 2FA |
| Homebase write endpoints | Confirmed working |
| LineLeader reschedule endpoint | Confirmed — `PUT /api/v3/tasks/{item_id}` |
| Child name lookup from family | Confirmed — `GET /families/{id}` → `children[]` |
| GBS vs JR GBS distinction | Confirmed — description field + `custom_values JUNIOR` fallback |
| Cookie persistence (MyStudio) | Confirmed — cookies persist 30 days with `remember_me: true` |

### ⚠️ Known Limitations
| Issue | Workaround |
|-------|-----------|
| ~~Gmail App Passwords unavailable~~ | ✅ Resolved (M8) — `eastvalechinocodeninjas@gmail.com` is a regular Gmail account. Enabled 2-Step Verification + created app password. OTP is now auto-extracted via IMAP. |
| Ollama tool calling unreliable | Ollama models ignore tool definitions. Use `TEST_MODE=true` for cost-free testing instead. |
| **All-future cancel does not cascade** | `cancel_registration_type: "Y"` returns Success but only deletes the targeted occurrence — future recurring sessions remain. Single cancel (`"N"`) works correctly. Root cause unknown — may need additional params. Under investigation. |
| **All-future reschedule does not cascade** | `allow_recurring_reschedule: "Y"` + `selected_reschedule_type: "Y"` returns Success but future occurrences are not moved. Single reschedule works. Same root cause as above. |
| **Book new appointment blocked** | `stripeClassAppointmentRegistration` requires a student-session token from the POS flow — not available from staff auth. Deferred until token source identified. |
| **"Monday" resolves to nearest Monday from today** | When moving a session that is itself in the future (e.g. "move June 13 to Monday"), "Monday" resolves relative to today, not relative to June 13. Workaround: specify explicit date ("June 15"). Fix: after resolving to_date, if it falls before from_date, roll forward 7 days. |
| ~~Camp roster blocked~~ | ✅ Fixed (M3b) — root cause was missing `X-Requested-With: XMLHttpRequest` header + session-level `Content-Type: application/json` overriding form POST encoding + missing `c_u_id_9901` email cookie. |

### 🔄 In Progress / Untested
| Question | Notes |
|----------|-------|
| Does MyStudio rate-limit repeated logins? | Watch for 429 errors if testing OTP flow repeatedly |
| All-future recurring ops root cause | Need DevTools capture of browser's recurring cancel/reschedule to compare params |
| Employee schedule generation | Stretch goal (Milestone 6) |
| Camp details milestone | Separate milestone (3b) — needs own plan and API discovery |

---

## Milestone 7 — Railway Deployment (Public Launch)

**Goal:** Deploy the Flask app to Railway so staff and others can access it from any device without running it locally.

**Why Railway:** Existing deployment plan already committed (`105646d`). Supports Python, persistent storage for cookie cache, environment variables for secrets, and auto-deploy from GitHub.

**Key challenges for cloud deployment:**
- `browser_state/` cookie files must persist across deploys (Railway volume or environment variable injection)
- MyStudio OTP flow: auto-handled via Gmail IMAP (M8 complete) — no manual entry needed on first deploy
- `ANTHROPIC_API_KEY` and all `.env` values go into Railway environment variables — never in code
- Port: Railway sets `PORT` env var — update `app.run()` to use `int(os.getenv("PORT", 5001))`

**Open a new chat and reference the existing Railway deployment plan in git history (`git show 105646d`) to execute.**

---

## Milestone 8 — Auto Gmail OTP Extraction ✅ Complete

**What it does:** When MyStudio cookies expire (every 30 days), the app automatically reads the OTP from Gmail and completes login — no human in the loop.

**How it works:**
1. Before sending MyStudio credentials, snapshot the inbox's highest message UID
2. Send credentials → MyStudio emails OTP to `eastvalechinocodeninjas@gmail.com`
3. Poll Gmail via IMAP every 3 seconds for a new message (UID > snapshot)
4. Parse the email's plain text / stripped HTML, extract 6-digit code via regex
5. Submit OTP automatically → cookies cached for 30 days

**Key files:**
- `core/gmail_imap.py` — `get_2fa_code_from_gmail()` + `get_inbox_max_uid()`
- `sites/mystudio/auth.py` — `_get_inbox_uid_snapshot()`, `_try_auto_otp()` wired into `_start_login()`

**One-time setup (already done):**
1. Enabled 2-Step Verification on `eastvalechinocodeninjas@gmail.com`
2. Created Gmail app password at myaccount.google.com/apppasswords
3. Added `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` to `.env`

**Fallback:** If Gmail credentials are missing or polling times out, falls back to `MystudioOTPRequired` — user is prompted in the chat UI as before.

**To test:** `python3 test_mystudio_login.py` (clears cookies and runs the full auto-OTP flow)

---

---

# APPENDIX: Detailed Technical Reference

## Site 1 — MyStudio API Reference (Milestone 2)

**Base URL:** `https://cn.mystudio.io/v43/Api/PortalApi/`

**Auth method:** Session cookies (PHP-based), persisted 30 days with `remember_me: true`

**Company IDs (Code Ninjas Eastvale Chino):**
- `company_id = "578"`
- `user_id = "9901"`
- Login email: `eastvalechinocodeninjas@gmail.com`

### Login Flow

1. **Step 1:** POST `/Api/PortalApi/login`
   ```json
   {
     "email": "eastvalechinocodeninjas@gmail.com",
     "password": "base64(urllib.parse.quote(password, safe=''))",
     "from": "login_form"
   }
   ```
   Response: OTP email sent to inbox

2. **Step 2:** POST `/Api/PortalApi/login` (with OTP)
   ```json
   {
     "otpCode": "base64(urllib.parse.quote('6_digit_code', safe=''))",
     "from": "otp_form",
     "remember_me": true
   }
   ```
   Response: Session cookies set (`PHPSESSID`, `c_u_id_9901_sessid`, `ms_trace_id`, `ms_u_em`)

**Critical detail:** Password/OTP encoding uses `safe=''` parameter. The `@` in email must encode to `%40`.

### API Endpoints

| Endpoint | Method | Purpose | Query Params |
|----------|--------|---------|--------------|
| `getClassScheduledetails` | GET | Fetch class time slots | `company_id`, `selected_date`, `class_scheduler_verion=2`, `view_roster_flag=N` |
| `getClassdatatabledetails` | POST | Student roster for a slot | Form-encoded, DataTables format (23-column headers required) |
| `verifySession` | GET | Check session validity | None |
| `getstudent` | POST | Search participants by name | DataTables form-encoded, 12 columns |
| `getParticipantRegDetails` | GET | Full student profile, rank, membership, sessions | `company_id`, `participant_id`, `student_id`, `mobile_view=N` |
| `getParticipantRegDetailsByType` | GET | Filtered session list (past/upcoming) | `class_filter_type=P\|U`, `class_filter_date`, `class_filter_days_value`, `show_more_type=A` |
| `membersRegDetails` | POST | Membership plan details: frequency, billing cycle dates | JSON body: `company_id`, `selected_membership_id` (= reg_id), `franchise_master_id=5`, `franchise_program_id=9` |
| `removeParticipant` | POST | Cancel a student session | JSON body via v43/Api/PortalApi |
| `RescheduleCurrentAppointment` | POST | Move a student session | JSON body via Api/v2 |

### StudentAppointment Fields (from API response)

| Field | Source | Example |
|-------|--------|---------|
| `id` | `class_reg_id` | `"12345"` |
| `student_name` | `Participant` | `"Journei Ashbourne"` |
| `student_id` | API response `student_id` | `"98765"` |
| `parent_name` | `Buyer` | `"Wittie Hughes"` |
| `phone` | `Phone` | `"(415) 815-9602"` |
| `rank` | `rank_status` | `"White Belt"` |
| `appointment_type` | Class title | `"CREATE (CODING)"` or `"JR"` |
| `start_time` | Slot `start_time` | `"2026-06-01 09:00:00"` |
| `end_time` | Student record | `"2026-06-01 16:00:00"` |

### Known Implementation Details

**DataTables request format is mandatory:** The `getClassdatatabledetails` endpoint requires all 23 column definitions, not just minimal form data. Missing columns returns 500 error.

Example columns array (partial):
```
columns[0][data]=""
columns[1][data]="show_icon"
columns[2][data]="Participant"
columns[3][data]="Buyer"
... (through columns[22][data]="")
```

**Session cookie caching:** Cookies cached to `browser_state/mystudio_cookies.json`. On day 31, app automatically prompts for new OTP. This IS the intended design, not a workaround.

**Limitations:**
- Gmail App Passwords unavailable (Google Workspace admin disabled them)
- OTP entry is manual (user reads email, types 6-digit code in terminal)

---

## Site 2 — LineLeader (ChildCareCRM) Architecture (Milestone 1)

**Key discovery:** LineLeader is owned by ChildCareCRM. Login at `login.lineleader.com` → redirects to `my.childcarecrm.com`. API at `live.childcarecrm.com/api/v3/`

**Base URL:** `https://live.childcarecrm.com/api/v3/`

**Auth method:** OAuth2 PKCE flow → Bearer JWT token (cached ~1 hour, 5-min safety buffer)

**Organization IDs (Code Ninjas Eastvale Chino):**
- `org_id = 101178`
- `center_id = 102025`
- `staff_id = 58347`

### Auth Flow

```
1. Playwright logs in at login.lineleader.com (form submission)
   ↓
2. OAuth2 PKCE flow runs automatically (server generates CSRF + code challenges)
   ↓
3. Browser redirects to my.childcarecrm.com
   ↓
4. App calls POST /api/v3/sso/login → returns Bearer JWT
   ↓
5. Token cached to browser_state/lineleader_token.json (exp time + 5-min buffer)
   ↓
6. All subsequent API calls use: Authorization: Bearer <token>
```

**Why Playwright for login:** OAuth2 PKCE uses cryptographic code challenges and server-generated CSRF tokens across a multi-step redirect chain. Cannot replicate with raw requests.

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /sso/login` | POST | Validate session, return Bearer JWT |
| `GET /action-items?task_dash_dates[0]=today&org_id=101178` | GET | Today's sessions/tours |
| `GET /action-items?task_dash_dates[0]=future&org_id=101178` | GET | Upcoming sessions |
| `GET /tasks/{item_id}` | GET | Full task object (needed before reschedule) |
| `PUT /tasks/{item_id}` | PUT | Update task (reschedule, cancel, etc.) |
| `GET /families/{family_id}` | GET | Full family record including children[] |
| `GET /staff/58347` | GET | Logged-in user info |
| `GET /centers/102025` | GET | Center details |

### Reschedule Endpoint

```
PUT https://live.childcarecrm.com/api/v3/tasks/{item_id}
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body (full object required):**
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
- `due_date_time` — ISO 8601 UTC — **this is the field that changes for reschedule**
- `type: 89` — Task type ID for Tours (GBS)
- `family` — Family ID (integer)
- `duration` — Session length in minutes (30 default)
- Full object must be sent (GET first, modify, then PUT)

### GBSSession Fields

| Field | Source |
|-------|--------|
| `student_name` | Guardian first + last name (from action-items) |
| `start_time` | `date_time` converted from UTC to local |
| `tour_type` | `"GBS"` or `"JR GBS"` — determined by description field (contains "JR") or custom_values.JUNIOR fallback |
| `item_id` | Task ID (used for GET/PUT reschedule) |
| `assignee_name` | Staff member name |
| `family_id` | Populated by enrichment step |
| `child_names` | List of child names — populated by enrichment (two-step API lookup) |
| `child_display` | `"Name (Xy)"` format for table display |

### Family Enrichment

Child names are NOT returned in the action-items response. Two-step lookup required:
1. `GET /tasks/{item_id}` → extract `family.id`
2. `GET /families/{family_id}` → extract `children[]` array

**Important:** Child's last name often differs from guardian's (e.g., Wittie Hughes → child: Journei Ashbourne). Child name matching is essential for NLP queries.

**Age calculation:** `date_of_birth` ISO string → `_calculate_age()` → display as `"Name (Xy)"` in table.

### Login Form Selectors

- Username: `#username` (name="_username")
- Password: `#password` (name="_password")
- Submit: `button[type="submit"]`

---

## Users & Permissions

| Role | Access |
|------|--------|
| Owner + Wife | All tasks including employee schedule (Milestone 6) |
| Staff (1 person) | Tasks 1–5 only — employee schedule completely hidden |

Owner identity enforced at session start via PIN or separate launch mode.
