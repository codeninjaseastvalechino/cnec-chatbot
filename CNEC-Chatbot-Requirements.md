# CNEC Chatbot — Requirements Document
**Version 1.1 | Status: Reviewed & Updated | May 2026**

---

## 1. Project Overview

An AI-powered automation agent for **Code Ninjas Eastvale** that accepts natural language instructions from a small team and executes scheduling, data retrieval, and administrative tasks across three platforms. The agent is operated via a local chat-style interface using browser automation (Playwright) and direct API calls where available.

> 🚀 **Long-term vision:** If successful, this could be packaged and sold to other Code Ninjas centers as a multi-tenant SaaS product. The system will be built config-driven from the start to support this path.

---

## 2. Websites & Site Map

| ID | Platform | URL | Auth | Integration Method |
|----|----------|-----|------|--------------------|
| **Site 1** | MyStudio | cn.mystudio.io | Username + password + email 2FA | Playwright + API interception |
| **Site 2** | LineLeader Enroll | login.lineleader.com | Username + password | Playwright + API interception |
| **Site 3** | Homebase | app.joinhomebase.com | Username + password (owner only) | Homebase API — no browser scraping needed |

- Sites are **mostly siloed** — data does not sync between them automatically
- System designed to **accommodate additional sites** in the future
- MyStudio and LineLeader require live site inspection to map data endpoints (next step)

---

## 3. Task Inventory

Tasks listed in **priority order** for implementation.

---

### 3.1 Daily Student Schedule — Priority 1 — Sites 1 + 2

**Trigger:** "What does today's schedule look like?" or similar

- Pull all student appointments for today from **MyStudio (Site 1)**
- Pull all GBS (Game Building Sessions) for today from **LineLeader (Site 2)**
- Merge both into a single unified list ordered chronologically by time slot
- Label each entry by type: Student Appointment vs. GBS

**Output:** Chat summary + downloadable Excel/CSV file

---

### 3.2 Move a Student — Priority 2 — Site 1

**Trigger:** "Move [student] from their 3pm to Friday at 2pm"

- Locate the student's current appointment
- Verify the target slot is available
- **Confirm with user before making any change**
- Reschedule the appointment

**Output:** Confirmation message + updated time

---

### 3.3 Create or Cancel Appointment — Priority 3 — Site 1

**Trigger:** "Cancel [student]'s session Thursday" / "Book [student] for Monday at 4pm"

- Locate student / slot
- **Always confirm before taking action**
- Execute create or cancel

**Output:** Confirmation message

---

### 3.4 Student Lookup — Priority 4 — Site 1

**Trigger:** "How many days has [student] come this week? What's their upcoming schedule?"

- Search for a specific student by name
- Return: days attended this week + upcoming scheduled sessions

**Output:** Chat summary

---

### 3.5 Camp Details — Priority 5 — Site 1

**Trigger:** "What camps are coming up? How many kids are in [camp]?"

- Retrieve list of upcoming camps
- For a specific camp: name, dates, enrolled student count, roster if available

**Output:** Chat summary

---

### 3.6 Employee Schedule Generator — Stretch Goal — Site 3

**Trigger:** Owner/wife only — "Draft next week's employee schedule"

> ⚠️ **Owner-only access.** No staff member may trigger, view, or interact with this task in any way — including read-only. Task is not visible to staff in the UI.

- Pull current/past schedules and team availability from Homebase API
- Pull upcoming camp data from MyStudio (Site 1) to inform staffing needs
- Factor in employee time-off requests visible in Homebase
- Use AI reasoning to propose a draft weekly schedule
- **Present draft in chat — ask for approval before publishing**
- On approval: push finalized schedule to Homebase via API

**Output:** Chat-formatted draft → published to Homebase on owner confirmation

---

## 4. User Interface

- **Primary interface:** Local chat window (web UI) or CLI
- Users type natural language instructions; agent responds in the same window
- Downloadable Excel/CSV output for schedule and data exports
- **Deployment:** Locally hosted on up to 3 machines (1 Windows, 2 Mac)
- **Future:** Cloud-hosted web app if expanded to other Code Ninjas centers

---

## 5. Users & Permissions

| Role | Users | Access |
|------|-------|--------|
| **Owner** | Owner + Wife (2 people) | All tasks including Task 3.6 (employee schedule) |
| **Staff** | Up to 1 additional team member | Tasks 3.1–3.5 only |

- No chatbot login required — agent authenticates to sites on behalf of users
- Owner identity for Task 3.6 enforced at session start (e.g. owner PIN or separate launch mode)

---

## 6. Authentication & Session Management

### Site 1 — MyStudio (2FA)
- Login: username + password → email 2FA code
- 2FA inbox: shared team **Outlook / Microsoft 365** account
- 2FA retrieval: **Microsoft Graph API** — poll inbox for latest code on login
- Sessions persist hours/days → **browser state (cookies) cached to disk**, re-auth only on expiry

### Site 2 — LineLeader
- Login: username + password only
- Sessions cached via Playwright browser state

### Site 3 — Homebase
- Accessed via **Homebase API** — no browser automation needed
- Credentials **never stored in .env** — entered by owner at runtime, held in memory only
- Alternative if needed: password-protected .env readable only by owner OS account

### Credential Storage Summary

| Site | Storage Method | Reason |
|------|---------------|--------|
| MyStudio (Site 1) | Local `.env` file | All staff have site access anyway |
| LineLeader (Site 2) | Local `.env` file | All staff have site access anyway |
| Homebase (Site 3) | Runtime prompt — never saved | Staff must not have access to employee/owner data |
| Microsoft Graph (2FA) | Local `.env` file | Client ID + secret for Outlook inbox polling |

---

## 7. Automation Strategy

| Site | Method | Headless Mode |
|------|--------|---------------|
| MyStudio (Site 1) | Playwright + network API interception | Read tasks: headless / Write tasks: visible |
| LineLeader (Site 2) | Playwright + network API interception | Read tasks: headless / Write tasks: visible |
| Homebase (Site 3) | Direct Homebase API calls | N/A — no browser |

> ✅ Homebase API confirmed working. No rate limiting observed. 2FA manageable via Microsoft Graph same as Site 1.

---

## 8. Confirmation & Safety Rules

| Scenario | Agent Behavior |
|----------|---------------|
| Any write action (reschedule, create, cancel, publish) | Always ask user to confirm before proceeding |
| Ambiguous input (e.g. two students named "John") | Stop and ask user to clarify |
| Unexpected data on site (slot missing, page changed) | Flag and stop — do not touch anything |
| Site unreachable or automation failure | Stop immediately and report to user |
| Staff attempts to trigger Task 3.6 | Refuse — task not visible to staff |

---

## 9. Error Handling

| Error Type | Response |
|------------|----------|
| Site down / timeout | Immediately notify user; do not retry silently |
| Element not found / page structure changed | Notify user; log the failure |
| 2FA code not received within timeout | Notify user; halt login attempt |
| Ambiguous task input | Ask clarifying question before proceeding |
| Unexpected site state | Halt, do not modify anything, report to user |

---

## 10. Output Formats

| Task | Output |
|------|--------|
| Daily schedule (3.1) | Chat summary (merged, time-ordered) + downloadable Excel/CSV |
| Move student (3.2) | Chat confirmation |
| Create / cancel (3.3) | Chat confirmation |
| Student lookup (3.4) | Chat summary |
| Camp details (3.5) | Chat summary |
| Employee schedule draft (3.6) | Chat-formatted draft table |
| Employee schedule final (3.6) | Published to Homebase via API after owner approval |

---

## 11. Audit Logging

Every agent action is logged automatically with:

- **Timestamp**
- **Task type** and natural language input provided
- **Actions taken** (or attempted) on each site
- **Outcome** (success / failed / cancelled by user)

No user identity tracked — the chatbot has no login. Log stored locally as structured JSON or SQLite. Viewable on request.

---

## 12. Infrastructure & Deployment

| Attribute | Value |
|-----------|-------|
| Platform | Windows + Mac (locally hosted, up to 3 machines) |
| Language | Python (Playwright + Graph API + Homebase API ecosystem) |
| Run modes | On-demand (user triggers) + Scheduled (e.g. daily morning schedule pull) |
| Scheduler | APScheduler or system cron |
| Maintainer | Owner only |
| Secrets | .env file (Sites 1 & 2); runtime prompt only (Site 3) |
| Future hosting | Cloud web app if scaled to other Code Ninjas centers |

---

## 13. Build Plan — Incremental Milestones

### Milestone 1 — First Working Demo
- Set up Python project structure (Playwright, config, logging)
- Implement LineLeader (Site 2) login — simplest auth, no 2FA
- Pull today's GBS sessions from LineLeader
- Display output in CLI

### Milestone 2 — Full Daily Schedule
- Implement MyStudio (Site 1) login with 2FA via Microsoft Graph API
- Session caching for both sites
- Pull today's student appointments from MyStudio
- Merge Sites 1 + 2 into unified time-ordered schedule
- Output: chat summary + Excel/CSV download

### Milestone 3 — Read Tasks
- Student lookup (attendance count + upcoming schedule)
- Camp details (upcoming camps, enrollment counts)

### Milestone 4 — Write Tasks
- Move a student (with confirmation flow)
- Create / cancel appointments (with confirmation flow)

### Milestone 5 — Chat UI & Scheduling
- Natural language chat window interface
- Scheduled daily run (morning schedule pull)
- Audit logging (JSON or SQLite)
- Owner vs. staff permission gating

### Milestone 6 — Employee Schedule Generator (Stretch Goal)
- Homebase API integration (availability, past schedules, time-off)
- Cross-reference with MyStudio camp data
- AI-assisted schedule drafting
- Owner-only access gate + runtime credential prompt
- Confirm-and-publish flow via Homebase API

---

## 14. Open Questions

| # | Question | Status |
|---|----------|--------|
| 1 | Which specific pages/endpoints on MyStudio and LineLeader contain the needed data? | 🔄 Needs live site inspection |
| 2 | Does MyStudio rate-limit or bot-detect Playwright traffic? | 🔄 Test early; use gentle pacing |
| 3 | Homebase schedule format and API endpoints for writing schedules | ✅ Weekly grid confirmed; API confirmed working |
| 4 | User identity in chat UI | ✅ No tracking — actions + timestamps only |
| 5 | Chat UI hosting | ✅ Local (3 machines); cloud later if scaled |

---

*Document updated after requirements review session — May 2026.*
*Next step: Live site inspection of MyStudio and LineLeader to resolve Open Question #1.*