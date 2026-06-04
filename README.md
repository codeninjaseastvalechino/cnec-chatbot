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
ANTHROPIC_API_KEY=sk-ant-...   # only needed for web UI
```

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

### Authentication
- **LineLeader:** Logs in automatically, token cached for ~1 hour
- **MyStudio:** Cookie cached for 30 days — when it expires, the chatbot prompts for a 6-digit OTP (sent to the center email) directly in the browser chat

### Planned
- ⬜ Quick-query shortcut buttons (common queries that skip Claude entirely — faster, free)
- ⬜ Student lookup by name
- ⬜ Camp enrollment details
- ⬜ Create / cancel appointments
- ⬜ Employee schedule (Homebase)
- ⬜ Cloud hosting (accessible from anywhere, not just same WiFi)

---

## Project Status

| Milestone | Feature | Status |
|-----------|---------|--------|
| 1 | LineLeader login + GBS tours + reschedule (CLI) | ✅ Complete |
| 2 | MyStudio login + unified schedule + Excel export | ✅ Complete |
| 3 | Student lookup + camp details | ⬜ Planned |
| 4 | Create / cancel / move appointments | ⬜ Planned |
| 5 | Web chat UI + Claude API + function calling | ✅ Complete |
| 6 | Employee schedule (Homebase) | ⬜ Backlog |

---

## File Overview

```
cnec-chatbot/
├── app.py              — Flask web server (the main thing to run)
├── chatbot.py          — Claude API integration + tool routing
├── analytics.py        — Tracks queries/tools for usage insights
├── audit_log.py        — Full interaction log (every message)
├── format_tours.py     — Formats schedule data as readable bullets
├── export_tours.py     — Generates Excel files
│
├── sites/
│   ├── lineleader/     — LineLeader / ChildCareCRM integration
│   └── mystudio/       — MyStudio integration
│
├── config/settings.py  — All center-specific config (IDs, URLs)
├── logs/               — Operation logs, audit trail, query analytics
├── exports/            — Excel files land here
└── browser_state/      — Cached auth tokens/cookies
```

---

## Troubleshooting

**Login fails / no data**
```bash
rm -f browser_state/lineleader_token.json   # clear cached token, force fresh login
python3 run_milestone1.py                    # test LineLeader connection directly
```

**MyStudio asks for OTP every time**
That's expected when cookies expire (~30 days). Enter the 6-digit code from the center email in the chat. Cookies are then cached for another 30 days.

**"No tours today" but tours exist in LineLeader**
Verify the date — the chatbot uses the system clock. You can ask explicitly: *"Show me tours for June 5"*

**Can't reach from another machine**
Make sure Python is allowed through the Mac firewall:
System Settings → Network → Firewall → Firewall Options → add `.venv/bin/python3`

---

## For Developers

Full technical docs — architecture decisions, API endpoints, auth flows, debugging — are in **[CLAUDE.md](CLAUDE.md)**.
