# Railway Deployment Plan — CNEC Chatbot

## Context
Deploy the Flask-based CNEC chatbot to Railway Free tier ($1/month after 30-day trial).
Key goal: persistent `browser_state/` volume so MyStudio 30-day cookies and LineLeader
tokens survive restarts and redeploys — eliminating OTP re-entry during active development.

---

## Files to Create/Modify

### 1. `Procfile` (new, 1 line)
```
web: python app.py
```

### 2. `.python-version` (new, 1 line)
```
3.9
```
Tells Nixpacks (Railway's auto-builder) to use Python 3.9, matching the project constraint.

### 3. `app.py` — 1 line change (line 696)
Railway injects a `PORT` environment variable. The app must listen on it.

**Before:**
```python
app.run(host="0.0.0.0", port=5001, debug=True)
```
**After:**
```python
port = int(os.getenv("PORT", 5001))
app.run(host="0.0.0.0", port=port, debug=False)
```

---

## Railway Dashboard Setup (done once, in browser)

### Step 1 — Create project
- railway.com → New Project → Deploy from GitHub repo → select `cnec-chatbot`
- Railway auto-detects Python via `requirements.txt` + `Procfile`

### Step 2 — Add persistent volumes (2 mounts, same volume)
- Service → Volumes → Add Volume → mount at `/app/browser_state`
- Service → Volumes → Add Volume → mount at `/app/logs`
- Size: 1 GB total (well within 0.5 GB free tier limit for both combined)

`browser_state/` persists auth tokens and cookies across restarts.
`logs/` persists `audit.jsonl` and `query_analytics.jsonl` across restarts and redeploys.

### Step 3 — Set environment variables
In Service → Variables, add all credentials from your `.env`:

| Variable | Value |
|---|---|
| `LINELEADER_USERNAME` | (from .env) |
| `LINELEADER_PASSWORD` | (from .env) |
| `MYSTUDIO_USERNAME` | (from .env) |
| `MYSTUDIO_PASSWORD` | (from .env) |
| `MYSTUDIO_COMPANY_ID` | (from .env) — **required**, app won't boot without it |
| `MYSTUDIO_USER_ID` | (from .env) — **required**, app won't boot without it |
| `ANTHROPIC_API_KEY` | (from .env) |
| `LLM_PROVIDER` | `claude` |
| `CLAUDE_MODEL` | `claude-haiku-4-5` |
| `SECRET_KEY` | random hex — `python3 -c "import secrets; print(secrets.token_hex(32))"` (set once; changing it logs everyone out) |
| `CENTER_TIMEZONE` | `America/Los_Angeles` |
| `TZ` | `America/Los_Angeles` (needed for correct LineLeader tour times on the UTC host) |

### Step 4 — Deploy
Push the 3 file changes to GitHub → Railway auto-deploys.
Railway gives you a public URL like `cnec-chatbot-production.up.railway.app`.

---

## First-time Auth (one-time after deploy)

1. Open the Railway URL in browser
2. Ask anything that needs MyStudio data (e.g. "What's today's schedule?")
3. App responds with OTP prompt in the chat UI
4. Check `eastvalechinocodeninjas@gmail.com` → enter 6-digit code in chat
5. Done — cookies cached to the volume, won't be asked again for 30 days

LineLeader auth happens silently in the background on first request (~2-3 seconds).

---

## Verification
- App loads at Railway URL ✅
- "What's today's full schedule?" returns real data ✅
- OTP flow works in browser UI (not terminal) ✅
- Excel download works ✅
- After a redeploy: query works without OTP prompt (cookies survived) ✅

---

## Reading Logs on Railway

### Real-time (Railway Dashboard)
Service → Logs tab captures all stdout. The console handler in `core/logger.py` writes
`INFO+` here — every tool call, request timing, and error shows up automatically.

### Query history (HTTP endpoints)
These are the primary interface for reading log data after the fact:
- `your-app.railway.app/api/audit-log` — every user message + full response
- `your-app.railway.app/api/analytics` — top tools, top queries, timing data

### Full structured logs (files on volume)
With `logs/` mounted on the volume, these persist across restarts:
- `logs/audit.jsonl` — one JSON object per interaction
- `logs/query_analytics.jsonl` — tool call timing and intent data
- `logs/cnec_chatbot.log` — DEBUG-level structured JSON for deep debugging

---

## Notes
- `exports/` directory (Excel files) is ephemeral — fine, users download immediately
- Railway free trial: 30 days free, then $1/month
