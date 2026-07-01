# CNEC Chatbot

AI-powered scheduling assistant for **Code Ninjas Eastvale Chino**. Staff ask questions in plain English and the chatbot pulls live data from LineLeader and MyStudio — no logging into multiple systems, no copy-pasting.

---

## What It Does

**Ask anything about the schedule in natural language:**

> *"Show me today's schedule"*
> *"Any GBS tours on Friday?"*
> *"Who's coming in tomorrow?"*
> *"Reschedule the 3pm tour to 4:30"*
> *"Download today's schedule as Excel"*
> *"What camps are running next week?"*
> *"Who's enrolled in the Minecraft camp? How old are they?"*
> *"What camps are running for the week of July 17th?"*

The chatbot figures out which system to query (or both), fetches the data, and presents it in a clean, readable format. You can also download any schedule as an Excel file in one click.

---

## What It Connects To

| Platform | What We Get |
|----------|-------------|
| **LineLeader / ChildCareCRM** | GBS & JR GBS tour appointments — prospective families visiting the center |
| **MyStudio** | Enrolled student class sessions — CREATE CODING, SCRATCH PLUS, JR, etc. |
| **Homebase** | Employee schedule *(planned — not yet built)* |

Both LineLeader and MyStudio data appear in a single unified, time-ordered view.

---

## How to Run

### Setup (one time)
```bash
git clone https://github.com/codeninjaseastvalechino/cnec-chatbot.git
cd cnec-chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add credentials (see below)
```

### Credentials needed in `.env`
```
LINELEADER_USERNAME=venay.bhatia@codeninjas.com
LINELEADER_PASSWORD=your_password
MYSTUDIO_USERNAME=eastvalechinocodeninjas@gmail.com
MYSTUDIO_PASSWORD=your_password
MYSTUDIO_COMPANY_ID=578        # required — center's MyStudio company id (Eastvale Chino: 578)
MYSTUDIO_USER_ID=9901          # required — center's MyStudio staff id (Eastvale Chino: 9901)
ANTHROPIC_API_KEY=sk-ant-...   # only needed for web UI
SECRET_KEY=...                 # required for web UI — signs session cookies (see below)
CENTER_TIMEZONE=America/Los_Angeles   # anchors the assistant's sense of "today"
TZ=America/Los_Angeles                # keeps LineLeader tour times / logs in local time
```

> The app **fails to start** if `MYSTUDIO_COMPANY_ID`, `MYSTUDIO_USER_ID`, or the
> LineLeader credentials are missing — this is intentional (a missing center id
> must not silently fall back to another center's data).
>
> Generate `SECRET_KEY` once with:
> `python3 -c "import secrets; print(secrets.token_hex(32))"`
> If it's unset the web UI still runs, but each browser's chat resets on every
> restart. See `.env.example` for the full list of optional keys.

### Start the web UI
```bash
# Real mode — live data, uses Claude API (~$0.001–0.005 per query)
python3 app.py

# Test mode — instant mock data, no API costs (good for UI work)
TEST_MODE=true python3 app.py
```

Open **http://localhost:5001** in any browser.  
Access from other devices on the same WiFi: **http://\<your-mac-ip\>:5001**

### CLI tool (LineLeader tours only, no API cost)
```bash
python3 run_milestone1.py
```

---

## Example Interaction

```
You:  Show me today's full schedule

Bot:  📅 Wednesday, June 3, 2026

      🔵 GBS Tours (LineLeader)
      ⏰ 5:00 PM — JR GBS
        👨‍👩‍👧 Parent: Wittie Hughes
        👧 Child: Journei Ashbourne (4y)
        👤 Staff: Venay Bhatia

      🟢 Student Classes (MyStudio)
      ⏰ 9:00 AM — CREATE CODING
        • Alice Chen (Blue Belt) — Parent: Jennifer Chen
        • Marcus Lee (White Belt) — Parent: David Lee
        ... 4 more students

      📥 Download as Excel → [Today's Schedule]
```

---

## Features

### Right Now
- ✅ Ask about any date — today, tomorrow, any specific date
- ✅ GBS and JR GBS tours from LineLeader with child names and ages
- ✅ Student class sessions from MyStudio with parent names, belt ranks, phone numbers
- ✅ Unified schedule merging both systems in time order
- ✅ Reschedule tours with confirmation before any write
- ✅ Export any schedule to Excel (one click)
- ✅ Multi-turn conversation — ask follow-ups naturally
- ✅ Accessible from any machine on the same WiFi
- ✅ Query analytics — tracks what's asked most to improve the UI over time
- ✅ Summer camp details — list camps by week, enrollment counts, spots left (upcoming and past)
- ✅ Camp roster — who's enrolled in each camp, kid names and ages (past and upcoming)
- ✅ Camp name search — find any camp by keyword across all past and upcoming camps; fuzzy matching handles typos
- ✅ "Week of July 17th" style queries — resolves any date to the correct Mon–Fri week

### Authentication
- **LineLeader:** Logs in automatically, token cached for ~1 hour
- **MyStudio:** Cookie cached for 30 days — when it expires, the app automatically reads the OTP from Gmail and re-authenticates with no manual input needed

### Planned / In Progress
- ✅ ~~Student lookup by name~~ — live
- ✅ ~~Create / cancel appointments~~ (single session) — live
- ✅ ~~Cloud hosting~~ — live at cnec.up.railway.app
- ✅ ~~Camp enrollment details~~ — live (Milestone 3b)
- ⬜ Quick-query shortcut buttons (common queries that skip Claude entirely — faster, free)
- ⬜ Cancel / move all-future recurring sessions (API gap under investigation)
- ⬜ Book new appointment (blocked — requires POS-flow token not yet obtainable)
- ⬜ Employee schedule (Homebase — Milestone 6)
- ⬜ Features & roadmap panel in the UI (Milestone 9 — deferred until app revamp)

---

## Project Status

| Milestone | Feature | Status |
|-----------|---------|--------|
| 1 | LineLeader login + GBS tours + reschedule (CLI) | ✅ Complete |
| 2 | MyStudio login + unified schedule + Excel export | ✅ Complete |
| 3 | Student lookup by name | ✅ Complete |
| 3b | Camp details — list, roster, kid names + ages | ✅ Complete |
| 4 | Cancel / move appointments (single session) | ✅ Complete |
| 5 | Web chat UI + Claude API + function calling | ✅ Complete |
| 6 | Employee schedule (Homebase) | ⬜ Backlog |
| 7 | Railway cloud deployment | ✅ Complete — live at cnec.up.railway.app |
| 8 | Auto Gmail OTP extraction | ✅ Complete |
| 9 | Features & roadmap panel in the UI | ⏳ Deferred — waiting on app revamp |

---

## File Overview

```
cnec-chatbot/
├── app.py              — Flask web server (the main thing to run)
├── chatbot.py          — Claude API integration + tool routing
├── llm_provider.py     — LLM provider abstraction (Claude; extensible)
├── analytics.py        — Tracks queries/tools for usage insights
├── audit_log.py        — Full interaction log (every message)
├── format_tours.py     — Formats schedule data as readable bullets
├── export_tours.py     — Generates Excel files
│
├── core/
│   ├── date_utils.py   — Date/time resolution (all tools pass raw phrases here)
│   └── gmail_imap.py   — Gmail IMAP polling for auto OTP extraction (M8)
│
├── sites/
│   ├── lineleader/     — LineLeader / ChildCareCRM integration
│   └── mystudio/       — MyStudio integration (auth, schedules, students, write)
│
├── config/settings.py  — All center-specific config (IDs, URLs, credentials)
├── logs/               — Operation logs, audit trail, query analytics
├── exports/            — Excel files land here
└── browser_state/      — Cached auth tokens/cookies (git-ignored)
```

---

## Troubleshooting

**Login fails / no data**
```bash
rm -f browser_state/lineleader_token.json   # clear cached token, force fresh login
python3 run_milestone1.py                    # test LineLeader connection directly
```

**MyStudio re-authenticates automatically**
When cookies expire (~30 days), the app reads the OTP from Gmail automatically — no manual entry needed. If Gmail credentials are missing from `.env`, it will fall back to prompting for the code in the chat.

**"No tours today" but tours exist in LineLeader**
Verify the date — the chatbot uses the system clock. You can ask explicitly: *"Show me tours for June 5"*

**Can't reach from another machine**
Make sure Python is allowed through the Mac firewall:
System Settings → Network → Firewall → Firewall Options → add `.venv/bin/python3`

---

## For Developers

Full technical docs — architecture decisions, API endpoints, auth flows, debugging — are in **[CLAUDE.md](CLAUDE.md)**.
