# CNEC Chatbot

AI-powered automation agent for **Code Ninjas Eastvale Chino** that accepts natural language instructions and executes scheduling, data retrieval, and administrative tasks across three platforms:

| Platform | Purpose |
|----------|---------|
| LineLeader / ChildCareCRM | GBS Tour schedule, reschedule |
| MyStudio | Full daily schedule, student lookup |
| Homebase | Employee schedule |

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/codeninjaseastvalechino/cnec-chatbot.git
cd cnec-chatbot
```

### 2. Create your `.env`
```bash
cp .env.example .env
# Open .env and fill in real credentials
```

### 3. Install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Run

### Milestone 1 — Today's GBS Tours + Reschedule
```bash
source .venv/bin/activate
python3 run_milestone1.py
```

What it does:
- Logs in to LineLeader (headless browser, token cached for ~1 hour)
- Pulls today's GBS Tours with child names, ages, and tour type (GBS / JR GBS)
- Optionally reschedule a tour by number or name (guardian or child name)

---

## Milestones

| # | Feature | Status |
|---|---------|--------|
| 1 | LineLeader login + GBS Tour pull + reschedule | ✅ Complete |
| 2 | MyStudio login + 2FA + full daily schedule | ⬜ In progress |
| 3 | Student lookup + camp details | ⬜ Not started |
| 4 | Move / create / cancel appointments | ⬜ Not started |
| 5 | Chat UI + scheduler + audit log | ⬜ Not started |
| 6 | Employee schedule generator | ⬜ Not started |

---

## Project Structure

```
cnec-chatbot/
├── .env.example          ← copy to .env and fill in credentials
├── run_milestone1.py     ← CLI entry point
├── requirements.txt
├── config/
│   └── settings.py       ← all center-specific config lives here
├── core/
│   └── logger.py         ← structured JSON logging
└── sites/
    └── lineleader/
        ├── auth.py       ← login + Bearer token management
        └── schedules.py  ← API calls, session parsing, reschedule
```

---

## Notes

- Credentials are never hardcoded — all values live in `.env`
- The chatbot never writes to a live site without explicit user confirmation
- Homebase credentials are entered at runtime only and never saved to disk
- See `CLAUDE.md` for full technical architecture and API documentation
