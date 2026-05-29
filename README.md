# CNEC Chatbot

AI-powered automation agent for **Code Ninjas Eastvale Chino** that manages GBS Tour scheduling through natural language. Choose between a **CLI tool** (Milestone 1) or a **web chat interface** (Milestone 5) — both powered by the same LineLeader API.

| Platform | Purpose |
|----------|---------|
| LineLeader / ChildCareCRM | GBS Tour schedule, reschedule, details |
| MyStudio | Full daily schedule, student lookup *(Milestone 2 — coming soon)* |
| Homebase | Employee schedule *(Milestone 3 — coming soon)* |

---

## Setup (5 minutes)

### 1. Clone and install
```bash
git clone https://github.com/codeninjaseastvalechino/cnec-chatbot.git
cd cnec-chatbot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Create `.env` with credentials
```bash
cp .env.example .env
# Edit .env and add:
# LINELEADER_USERNAME=...
# LINELEADER_PASSWORD=...
# ANTHROPIC_API_KEY=...  (for web UI only)
```

### 3. Verify LineLeader credentials work
```bash
python3 run_milestone1.py
```

You should see today's GBS tours in a table.

---

## Run

### Milestone 1: CLI Tool (No API Costs)

```bash
python3 run_milestone1.py
```

**What it does:**
- Logs in to LineLeader (token cached ~1 hour)
- Shows today's GBS Tours in a formatted table
- Parent name, children (with ages), tour type, assigned staff
- Optionally reschedule by tour number or name

**Example:**
```
Today's GBS Tours — Friday, May 29, 2026
╭──────┬────────────┬────────────────────────┬──────────────┬───────────────────
│    # │ Time       │ Student                │ Tour Type    │ Child
├──────┼────────────┼────────────────────────┼──────────────┼───────────────────
│    1 │ 11:30 AM   │ Venay Bhatia           │ GBS          │
│    2 │ 3:00 PM    │ Kira Holland           │ JR GBS       │ Vaia Holland (6y)
│    3 │ 3:00 PM    │ Shabnam Moosajee       │ JR GBS       │ Aaliyah Moosajee (6y)
│    4 │ 4:00 PM    │ Erika Cuevas           │ GBS          │ Isaac Camargo (11y)
│    5 │ 4:30 PM    │ Eva Chen               │ GBS          │ Henry Jiao (13y)
│    6 │ 5:30 PM    │ Vashisth Thaker        │ GBS          │ Viyaan Thaker (7y)
```

---

### Milestone 5: Web Chat UI (Uses Claude API)

```bash
# Real mode (uses Claude API + LineLeader data)
python3 app.py

# Test mode (mock data, no API costs — great for development)
TEST_MODE=true python3 app.py
```

**What it does:**
- Starts Flask server on `http://localhost:5001`
- Code Ninjas branded chat UI with logo and colors
- Ask Claude in natural language about tours
- Claude uses function calling to execute operations
- Download schedules as Excel files

**Example chat:**
```
You: "Show me today's tours"

Claude:
📅 Friday, May 29
  ⏰ 11:30 AM
    👨‍👩‍👧 Venay Bhatia
    🎮 GBS
  ⏰ 3:00 PM
    👨‍👩‍👧 Kira Holland
    👧 Vaia Holland (6y)
    🎮 JR GBS

[... more tours ...]

📥 **Download as Excel:** [Download this schedule](/api/export/tours)
```

**What you can ask:**
- "What tours are scheduled today?"
- "Tell me about the 3pm tour"
- "Reschedule the 2pm tour to 4pm tomorrow"
- "Show me only JR GBS tours"
- "Download the schedule as Excel"

**Accessible from other machines on your WiFi:**
```
http://<your-ip>:5001
```

Find your IP: `ifconfig | grep inet`

---

## Features

### CLI (Milestone 1)
✅ Login to LineLeader with token caching  
✅ Show today's GBS tours in formatted table  
✅ Display parent, children (with ages), tour type, assigned staff  
✅ Reschedule tours with confirmation  
✅ Search/filter by name or number  

### Web UI (Milestone 5)
✅ Chat interface with Code Ninjas branding  
✅ Natural language questions about tours  
✅ Nested bullet format with emojis for readability  
✅ Multi-turn conversation (ask follow-ups)  
✅ Excel export with professional formatting  
✅ Audit log of all interactions  
✅ Test mode for development (no API costs)  
✅ Accessible from any machine on same WiFi  

---

## Project Status

| Milestone | Feature | Status |
|-----------|---------|--------|
| 1 | LineLeader login + GBS tours + reschedule (CLI) | ✅ Complete |
| 2 | MyStudio login + 2FA + full daily schedule | ⬜ Not started |
| 3 | Student lookup + camp details | ⬜ Not started |
| 4 | Move / create / cancel appointments | ⬜ Not started |
| 5 | Chat UI + Claude API + function calling + Excel export | ✅ Complete |
| 6 | Employee schedule generator | ⬜ Not started |

---

## Project Structure

```
cnec-chatbot/
├── README.md                 ← you are here
├── CLAUDE.md                 ← full technical briefing (for developers)
├── CNEC-Chatbot-Requirements.md
├── .env.example              ← copy to .env and fill in credentials
│
├── Milestone 1 (CLI)
├── run_milestone1.py         ← entry point: python3 run_milestone1.py
│
├── Milestone 5 (Web UI)
├── app.py                    ← Flask server + HTML/CSS/JS
├── chatbot.py                ← Claude API integration with function calling
├── mock_chatbot.py           ← Mock chatbot for testing (TEST_MODE=true)
├── format_tours.py           ← Format tour data as nested bullets with emojis
├── export_tours.py           ← Generate Excel files with formatting
├── audit_log.py              ← JSON audit logging
│
├── Core
├── requirements.txt
├── config/
│   └── settings.py           ← all center-specific config (org IDs, URLs)
├── core/
│   └── logger.py             ← structured JSON logging
│
├── Sites
└── sites/
    └── lineleader/
        ├── auth.py           ← Playwright login + Bearer token management
        └── schedules.py      ← ChildCareCRM API calls, parsing, reschedule
│
├── Output
├── asset/
│   └── cnec-logo.jpeg        ← Code Ninjas logo (web UI)
├── logs/
│   ├── cnec_chatbot.log      ← structured JSON logs
│   └── audit.jsonl           ← audit trail (one JSON object per line)
├── exports/                  ← Excel files saved here
└── browser_state/
    └── lineleader_token.json ← cached Bearer token + expiry
```

---

## Testing

### Test Milestone 1 (no dependencies)
```bash
python3 run_milestone1.py
```

### Test Milestone 5 without API costs
```bash
TEST_MODE=true python3 app.py
```

Then navigate to `http://localhost:5001` and chat away. Uses mock tour data.

### Test Milestone 5 with real API
```bash
python3 app.py
```

Requires valid `ANTHROPIC_API_KEY` in `.env`. Real LineLeader data.

---

## Troubleshooting

### "Bearer token invalid" or login fails
Your LineLeader credentials are stale or missing.
```bash
# Verify .env has credentials
cat .env | grep LINELEADER

# Test directly with Milestone 1
python3 run_milestone1.py

# Clear cached token and retry
rm -f browser_state/lineleader_token.json
python3 run_milestone1.py
```

### "ANTHROPIC_API_KEY not set" (Milestone 5 only)
Claude API can't authenticate.
```bash
# Check .env has your key
cat .env | grep ANTHROPIC_API_KEY

# Verify environment is sourced
echo $ANTHROPIC_API_KEY  # should print your key

# If empty, source again
source .venv/bin/activate
```

### "No tours scheduled for today"
Check the date and verify you have tours in LineLeader for today.
```bash
# Use Milestone 1 to verify
python3 run_milestone1.py
```

### Playwright issues
```bash
# Reinstall Playwright
playwright install chromium

# Or use headless=false to see the browser (CLAUDE.md for details)
```

---

## Safety & Design

- ✅ **No hardcoded credentials** — everything in `.env`
- ✅ **Confirmation before writes** — reschedule requires user approval
- ✅ **Audit trail** — JSON logs of all interactions
- ✅ **Token caching** — Bearer token cached ~1 hour (5-min safety buffer)
- ✅ **Multi-tenant ready** — config-driven, easy to deploy for other centers

---

## Documentation

- **CLAUDE.md** — Full technical briefing for developers (architecture, APIs, decisions, debugging)
- **CNEC-Chatbot-Requirements.md** — Complete product requirements

---

## Next Steps

**Milestone 2:** MyStudio integration
- Login with 2FA
- Full daily schedule (not just GBS tours)
- Student details lookup

**Milestone 3:** Homebase integration
- Employee schedule
- Shift publishing

**Milestone 4:** Extended operations
- Create new appointments
- Cancel appointments
- Move appointments

See CLAUDE.md for architecture decisions and confirmed API endpoints for each site.
