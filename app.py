"""
Flask web server for CNEC Chatbot with Claude API + function calling.

Runs on localhost:5001. Accessible from other machines on the same network
at http://<your-ip>:5001.
"""

from dotenv import load_dotenv
from pathlib import Path

# Load .env variables before other imports
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

import json
import os
from core.logger import get_logger
logger = get_logger(__name__)
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from datetime import datetime
from audit_log import AuditLogger
from analytics import QueryAnalytics
from config.settings import settings

app = Flask(__name__)
audit = AuditLogger()
analytics = QueryAnalytics()

# Cache last fetched schedule for Excel export (avoid double API calls)
_schedule_cache = {"gbs_sessions": [], "appointments": []}

# Use mock chatbot for testing (doesn't hit any LLM API)
if os.getenv("TEST_MODE", "").lower() == "true":
    print("🧪 TEST MODE ENABLED - Using mock chatbot (no LLM API calls)")
    from mock_chatbot import MockChatbotEngine
    chatbot = MockChatbotEngine()
else:
    from chatbot import ChatbotEngine
    from llm_provider import get_provider

    try:
        provider = get_provider()
        chatbot = ChatbotEngine(provider=provider)
    except RuntimeError as e:
        print(f"❌ Failed to initialize LLM provider: {e}")
        print("   Check your .env file and LLM_PROVIDER setting.")
        raise

# Serve logo from asset folder
@app.route("/asset/<path:filename>")
def serve_asset(filename):
    """Serve logo and other assets."""
    asset_path = Path(__file__).parent / "asset" / filename
    if asset_path.exists():
        return send_file(asset_path)
    return jsonify({"error": "Asset not found"}), 404


@app.route("/", methods=["GET"])
def index():
    """Serve the chat interface."""
    return """<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CNEC Chatbot</title>
        <style>
            :root {
                --cn-blue: #0052CC;
                --cn-orange: #FF6D00;
                --neutral-light: #F5F5F5;
                --neutral-bg: #FFFFFF;
                --text-primary: #1A1A1A;
                --text-secondary: #666666;
                --border-color: #E0E0E0;
            }

            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #f5f7fa 0%, #e9ecef 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }

            .container {
                width: 100%;
                max-width: 1200px;
                height: 90vh;
                max-height: 700px;
                background: var(--neutral-bg);
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                display: flex;
                flex-direction: row;
                overflow: hidden;
            }

            .chat-panel {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
            }

            .sidebar {
                width: 220px;
                flex-shrink: 0;
                background: var(--neutral-light);
                border-left: 1px solid var(--border-color);
                padding: 16px 12px;
                display: flex;
                flex-direction: column;
                gap: 8px;
                overflow-y: auto;
            }

            .sidebar h3 {
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-secondary);
                margin: 0 0 4px 0;
            }

            .quick-btn {
                width: 100%;
                padding: 9px 12px;
                background: white;
                color: var(--text-primary);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                text-align: left;
                transition: all 0.15s;
                line-height: 1.3;
                box-shadow: none;
                transform: none;
            }

            .quick-btn:hover:not(:disabled) {
                background: var(--cn-blue);
                color: white;
                border-color: var(--cn-blue);
                transform: none;
                box-shadow: none;
            }

            .sidebar-divider {
                height: 1px;
                background: var(--border-color);
                margin: 4px 0;
            }

            @media (max-width: 768px) {
                .sidebar { display: none; }
            }

            .header {
                background: linear-gradient(135deg, var(--cn-blue) 0%, #003d99 100%);
                color: white;
                padding: 20px;
                display: flex;
                align-items: center;
                gap: 16px;
                flex-shrink: 0;
            }

            .header img {
                height: 50px;
                width: auto;
                object-fit: contain;
            }

            .header-text h1 {
                font-size: 24px;
                font-weight: 600;
                margin: 0;
            }

            .header-text p {
                font-size: 12px;
                opacity: 0.9;
                margin: 4px 0 0 0;
            }

            #chat {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .message {
                display: flex;
                animation: slideIn 0.3s ease-out;
            }

            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .message.user {
                justify-content: flex-end;
            }

            .message.user .bubble {
                background: var(--cn-blue);
                color: white;
                border-radius: 18px 18px 4px 18px;
            }

            .message.assistant .bubble {
                background: var(--neutral-light);
                color: var(--text-primary);
                border-radius: 18px 18px 18px 4px;
            }

            .message.error .bubble {
                background: #FFE0E0;
                color: #C41C3B;
                border-radius: 18px;
            }

            .bubble {
                padding: 12px 16px;
                max-width: 75%;
                word-wrap: break-word;
                line-height: 1.5;
                font-size: 14px;
                white-space: pre-wrap;
                word-break: break-word;
            }

            .bubble a {
                color: var(--cn-blue);
                text-decoration: underline;
                cursor: pointer;
            }

            .excel-btn {
                display: inline-block;
                margin-top: 10px;
                padding: 6px 14px;
                background: #1D6F42;
                color: white !important;
                text-decoration: none !important;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
            }

            .excel-btn:hover {
                background: #155235;
            }

            .bubble table {
                margin: 8px 0;
                border-collapse: collapse;
                width: 100%;
            }

            .bubble table th {
                background: rgba(0, 0, 0, 0.05);
                padding: 8px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid rgba(0, 0, 0, 0.1);
            }

            .bubble table td {
                padding: 8px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.05);
            }

            .bubble table tr:last-child td {
                border-bottom: none;
            }

            .thinking {
                display: flex;
                align-items: center;
                gap: 8px;
                color: var(--text-secondary);
                font-size: 13px;
                padding: 12px 16px;
                background: var(--neutral-light);
                border-radius: 18px;
            }

            .dots {
                display: inline-flex;
                gap: 4px;
            }

            .dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                background: var(--text-secondary);
                animation: bounce 1.4s infinite;
            }

            .dot:nth-child(2) {
                animation-delay: 0.2s;
            }

            .dot:nth-child(3) {
                animation-delay: 0.4s;
            }

            @keyframes bounce {
                0%, 60%, 100% {
                    opacity: 0.6;
                    transform: translateY(0);
                }
                30% {
                    opacity: 1;
                    transform: translateY(-8px);
                }
            }

            .input-area {
                padding: 16px 20px;
                background: var(--neutral-bg);
                border-top: 1px solid var(--border-color);
                display: flex;
                gap: 12px;
                flex-shrink: 0;
            }

            #message {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid var(--border-color);
                border-radius: 24px;
                font-size: 14px;
                font-family: inherit;
                outline: none;
                transition: all 0.2s;
            }

            #message:focus {
                border-color: var(--cn-blue);
                box-shadow: 0 0 0 3px rgba(0, 82, 204, 0.1);
            }

            #message:disabled {
                background: var(--neutral-light);
                cursor: not-allowed;
                opacity: 0.6;
            }

            button {
                padding: 12px 28px;
                background: var(--cn-blue);
                color: white;
                border: none;
                border-radius: 24px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                flex-shrink: 0;
            }

            button:hover:not(:disabled) {
                background: var(--cn-orange);
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(255, 109, 0, 0.3);
            }


            button:active:not(:disabled) {
                transform: translateY(0);
            }

            button:disabled {
                background: #CCCCCC;
                cursor: not-allowed;
                opacity: 0.6;
            }

            .feature-request-btn {
                background: #f59e0b;
                width: 100%;
            }
            .feature-request-btn:hover:not(:disabled) {
                background: #d97706;
                box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
            }

            @media (max-width: 768px) {
                .container {
                    max-height: 100%;
                    border-radius: 0;
                }
                .bubble {
                    max-width: 90%;
                }
                .header h1 {
                    font-size: 20px;
                }
                .header img {
                    height: 40px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="chat-panel">
                <div class="header">
                    <img src="/asset/cnec-logo.jpeg" alt="Code Ninjas Eastvale Chino Logo">
                    <div class="header-text">
                        <h1>GBS Tour Assistant</h1>
                        <p>Code Ninjas Eastvale Chino</p>
                    </div>
                </div>

                <div id="chat"></div>

                <div class="input-area">
                    <input type="text" id="message" placeholder="Ask about tours or schedule..." autocomplete="off">
                    <button id="sendBtn" onclick="sendMessage();">Send</button>
                </div>
            </div>

            <div class="sidebar">
                <h3>Quick Actions</h3>
                <button class="quick-btn" onclick="quickSend('What is my full schedule today?')">📅 Full schedule today</button>
                <button class="quick-btn" onclick="quickSend('What GBS tours are scheduled today?')">🎮 Today\'s GBS tours</button>
                <button class="quick-btn" onclick="quickSend('Are there any JR GBS tours today?')">👶 JR GBS tours</button>
                <button class="quick-btn" onclick="quickSend('Download today\'s schedule as Excel')">📥 Download Excel</button>

                <div class="sidebar-divider"></div>
                <h3>Schedule</h3>
                <button class="quick-btn" onclick="quickSend('What is on the schedule for 3:00 PM?')">⏰ 3:00 PM slot</button>
                <button class="quick-btn" onclick="quickSend('How many students are coming today?')">👥 Student count</button>

                <div class="sidebar-divider"></div>
                <h3>Tours</h3>
                <button class="quick-btn" onclick="quickSend('How many tours are scheduled today?')">📊 Tour summary</button>
                <button class="quick-btn" onclick="quickSend('I need to reschedule a tour')">🔄 Reschedule tour</button>

                <div class="sidebar-divider"></div>
                <h3>Feedback</h3>
                <button class="quick-btn feature-request-btn" onclick="startFeatureRequest()">💡 Feature Request</button>
            </div>
        </div>

        <script>
        let isProcessing = false;

        function quickSend(text) {
            if (isProcessing) return;
            const input = document.getElementById('message');
            input.value = text;
            sendMessage();
        }

        function startFeatureRequest() {
            if (isProcessing) return;
            const input = document.getElementById('message');
            input.value = 'FEATURE REQUEST: ';
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
        }

        function parseMarkdownLinks(text) {
            return text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        }

        function addExcelButtonIfSchedule(responseText, bubbleElement) {
            // Match time patterns (e.g. "3:00 PM") or tour IDs as strong signals actual data was returned
            const hasScheduleData = /\d+:\d{2}\s*(AM|PM)/i.test(responseText) ||
                                    /\[ID:\s*\d+\]/.test(responseText);
            if (!hasScheduleData) return;
            const btn = document.createElement('a');
            btn.href = '/api/export/tours';
            btn.className = 'excel-btn';
            btn.textContent = '📥 Download as Excel';
            bubbleElement.appendChild(document.createElement('br'));
            bubbleElement.appendChild(btn);
        }

        function sendMessage() {
            const input = document.getElementById('message');
            const button = document.getElementById('sendBtn');
            const message = input.value.trim();
            if (!message || isProcessing) return;
            isProcessing = true;
            input.disabled = true;
            button.disabled = true;
            const chat = document.getElementById('chat');

            const userMsg = document.createElement('div');
            userMsg.className = 'message user';
            const userBubble = document.createElement('div');
            userBubble.className = 'bubble';
            userBubble.textContent = message;
            userMsg.appendChild(userBubble);
            chat.appendChild(userMsg);
            input.value = '';

            const thinkingMsg = document.createElement('div');
            thinkingMsg.className = 'message assistant';
            const thinkingBubble = document.createElement('div');
            thinkingBubble.className = 'thinking';
            thinkingBubble.innerHTML = '<span id="status-text">Thinking...</span><div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
            thinkingMsg.appendChild(thinkingBubble);
            chat.appendChild(thinkingMsg);
            chat.scrollTop = chat.scrollHeight;

            fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            }).then(r => r.json()).then(data => {
                thinkingMsg.remove();
                if (data.error) {
                    const errorMsg = document.createElement('div');
                    errorMsg.className = 'message error';
                    const errorBubble = document.createElement('div');
                    errorBubble.className = 'bubble';
                    errorBubble.textContent = 'Error: ' + data.error;
                    errorMsg.appendChild(errorBubble);
                    chat.appendChild(errorMsg);
                } else {
                    const assistantMsg = document.createElement('div');
                    assistantMsg.className = 'message assistant';
                    const assistantBubble = document.createElement('div');
                    assistantBubble.className = 'bubble';
                    assistantBubble.innerHTML = parseMarkdownLinks(data.response);
                    addExcelButtonIfSchedule(data.response, assistantBubble);
                    assistantMsg.appendChild(assistantBubble);
                    chat.appendChild(assistantMsg);
                }
                chat.scrollTop = chat.scrollHeight;
                isProcessing = false;
                input.disabled = false;
                button.disabled = false;
                input.focus();
            }).catch(err => {
                thinkingMsg.remove();
                const errorMsg = document.createElement('div');
                errorMsg.className = 'message error';
                const errorBubble = document.createElement('div');
                errorBubble.className = 'bubble';
                errorBubble.textContent = 'Error: ' + err.message;
                errorMsg.appendChild(errorBubble);
                chat.appendChild(errorMsg);
                isProcessing = false;
                input.disabled = false;
                button.disabled = false;
            });
        }
        document.getElementById('message').addEventListener('keypress', e => {
            if (e.key === 'Enter' && !isProcessing) sendMessage();
        });
        document.getElementById('message').focus();
        </script>
    </body>
    </html>
    """


FEATURE_REQUESTS_FILE = Path("logs/feature_requests.jsonl")


def _save_feature_request(text: str) -> None:
    FEATURE_REQUESTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FEATURE_REQUESTS_FILE, "a") as f:
        f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "request": text}) + "\n")
    logger.info("Feature request saved: %s", text)


@app.route("/api/feature-requests", methods=["GET"])
def get_feature_requests():
    """Return all saved feature requests."""
    try:
        if not FEATURE_REQUESTS_FILE.exists():
            return jsonify({"requests": []})
        entries = []
        with open(FEATURE_REQUESTS_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return jsonify({"requests": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle chat messages, streaming SSE status updates then final response."""
    data = request.json
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    audit.log_event("user_message", {"message": user_message})

    # Feature request — save to file and return immediately, no Claude call needed
    if user_message.upper().startswith("FEATURE REQUEST:"):
        request_text = user_message[len("FEATURE REQUEST:"):].strip()
        if request_text:
            _save_feature_request(request_text)
            return jsonify({
                "response": "✅ Thanks for the feedback! Your feature request has been saved and will be reviewed.",
                "statuses": []
            })
        else:
            return jsonify({
                "response": "Please describe your feature request after 'FEATURE REQUEST:'",
                "statuses": []
            })

    try:
        statuses = []
        response_text = chatbot.chat(user_message, status_callback=lambda msg: statuses.append(msg))
        audit.log_event("assistant_response", {"message": response_text})
        return jsonify({"response": response_text, "statuses": statuses})
    except Exception as e:
        logger.error("Chat error: %s", e)
        audit.log_event("error", {"error": str(e)})
        return jsonify({"error": str(e)}), 500


@app.route("/api/audit-log", methods=["GET"])
def get_audit_log():
    """Retrieve audit log entries (staff/owner only in production)."""
    try:
        entries = audit.read_log()
        return jsonify({"entries": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """
    Query analytics — most common queries, most called tools, recent history.

    GET /api/analytics             → full summary
    GET /api/analytics?recent=50   → last 50 entries
    """
    try:
        return jsonify({
            "top_intents": analytics.top_intents(limit=10),
            "top_tools":   analytics.top_tools(limit=10),
            "top_queries": analytics.top_queries(limit=10),
            "recent":      analytics.recent(limit=int(request.args.get("recent", 20))),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin")
def admin():
    """Password-protected admin dashboard — feature requests, analytics, recent queries."""
    password = request.args.get("pw", "")
    if password != settings.ADMIN_PASSWORD:
        return """
        <html><head><title>Admin Login</title>
        <style>
            body { font-family: sans-serif; display: flex; align-items: center;
                   justify-content: center; height: 100vh; margin: 0; background: #f3f4f6; }
            form { background: white; padding: 32px; border-radius: 12px;
                   box-shadow: 0 4px 16px rgba(0,0,0,0.1); text-align: center; }
            h2 { margin: 0 0 20px; color: #1a1a2e; }
            input { padding: 10px 16px; border: 1px solid #ddd; border-radius: 8px;
                    font-size: 14px; margin-right: 8px; }
            button { padding: 10px 20px; background: #FF6D00; color: white;
                     border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        </style></head><body>
        <form method="get">
            <h2>🔐 Admin Login</h2>
            <input type="password" name="pw" placeholder="Password" autofocus>
            <button type="submit">Enter</button>
        </form></body></html>
        """, 401

    return f"""
    <html><head><title>CNEC Admin</title>
    <style>
        body {{ font-family: sans-serif; margin: 0; background: #f3f4f6; color: #1a1a2e; }}
        .header {{ background: #1a1a2e; color: white; padding: 16px 32px;
                   display: flex; align-items: center; gap: 12px; }}
        .header h1 {{ margin: 0; font-size: 20px; }}
        .container {{ max-width: 1100px; margin: 32px auto; padding: 0 24px; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
        .card {{ background: white; border-radius: 12px; padding: 24px;
                 box-shadow: 0 2px 8px rgba(0,0,0,0.07); }}
        .card h2 {{ margin: 0 0 16px; font-size: 16px; color: #FF6D00; }}
        .card.full {{ grid-column: 1 / -1; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ text-align: left; padding: 8px; background: #f3f4f6;
              border-bottom: 2px solid #e5e7eb; }}
        td {{ padding: 8px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
        tr:last-child td {{ border-bottom: none; }}
        .empty {{ color: #999; font-style: italic; padding: 12px 0; }}
        .badge {{ display: inline-block; background: #e0f2fe; color: #0369a1;
                  border-radius: 12px; padding: 2px 8px; font-size: 11px; }}
        .refresh {{ float: right; font-size: 12px; color: #999; }}
    </style></head><body>
    <div class="header">
        <h1>CNEC Admin Dashboard</h1>
        <span style="margin-left: auto; font-size: 13px; opacity: 0.7;">Code Ninjas Eastvale Chino</span>
    </div>
    <div class="container">
        <div class="grid">
            <div class="card full" id="feature-requests">
                <h2>💡 Feature Requests <span class="refresh"><a href="/admin?pw={password}">↻ Refresh</a></span></h2>
                <div id="fr-content">Loading...</div>
            </div>
            <div class="card" id="top-tools">
                <h2>🔧 Most Used Tools</h2>
                <div id="tools-content">Loading...</div>
            </div>
            <div class="card" id="top-queries">
                <h2>💬 Most Common Queries</h2>
                <div id="queries-content">Loading...</div>
            </div>
            <div class="card full" id="recent-queries">
                <h2>🕐 Recent Activity</h2>
                <div id="recent-content">Loading...</div>
            </div>
        </div>
    </div>
    <script>
    async function load() {{
        // Feature requests
        const fr = await fetch('/api/feature-requests').then(r => r.json());
        const frEl = document.getElementById('fr-content');
        if (!fr.requests || fr.requests.length === 0) {{
            frEl.innerHTML = '<p class="empty">No feature requests yet.</p>';
        }} else {{
            const rows = fr.requests.slice().reverse().map(r =>
                `<tr><td style="color:#999;white-space:nowrap">${{r.ts.replace('T',' ').slice(0,16)}} UTC</td><td>${{r.request}}</td></tr>`
            ).join('');
            frEl.innerHTML = `<table><thead><tr><th>Submitted</th><th>Request</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        // Analytics
        const an = await fetch('/api/analytics').then(r => r.json());

        const toolsEl = document.getElementById('tools-content');
        if (!an.top_tools || an.top_tools.length === 0) {{
            toolsEl.innerHTML = '<p class="empty">No data yet.</p>';
        }} else {{
            const rows = an.top_tools.map(t =>
                `<tr><td>${{t.tool}}</td><td><span class="badge">${{t.count}}</span></td></tr>`
            ).join('');
            toolsEl.innerHTML = `<table><thead><tr><th>Tool</th><th>Calls</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        const queriesEl = document.getElementById('queries-content');
        if (!an.top_queries || an.top_queries.length === 0) {{
            queriesEl.innerHTML = '<p class="empty">No data yet.</p>';
        }} else {{
            const rows = an.top_queries.map(q =>
                `<tr><td>${{q.query}}</td><td><span class="badge">${{q.count}}</span></td></tr>`
            ).join('');
            queriesEl.innerHTML = `<table><thead><tr><th>Query</th><th>Count</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}

        const recentEl = document.getElementById('recent-content');
        if (!an.recent || an.recent.length === 0) {{
            recentEl.innerHTML = '<p class="empty">No activity yet.</p>';
        }} else {{
            const rows = an.recent.slice().reverse().map(r => {{
                const ts = (r.timestamp||'').slice(0,16).replace('T',' ');
                const tools = (r.tools||[]).map(t => t.name).join(', ') || '—';
                const dur = r.total_duration_s ? (r.total_duration_s.toFixed(1)+'s') : '';
                return `<tr>
                    <td style="color:#999;white-space:nowrap">${{ts}} UTC</td>
                    <td>${{r.query||''}}</td>
                    <td><span class="badge">${{tools}}</span></td>
                    <td style="color:#999">${{dur}}</td>
                </tr>`;
            }}).join('');
            recentEl.innerHTML = `<table><thead><tr><th>Time</th><th>Query</th><th>Tool</th><th>Duration</th></tr></thead><tbody>${{rows}}</tbody></table>`;
        }}
    }}
    load();
    </script>
    </body></html>
    """


@app.route("/api/export/tours", methods=["GET"])
def export_tours():
    """Export today's unified schedule (GBS tours + MyStudio appointments) to Excel."""
    try:
        from export_tours import create_unified_excel_file
        from sites.mystudio.appointments import StudentAppointment
        import asyncio

        if os.getenv("TEST_MODE", "").lower() == "true":
            from format_tours import get_sample_sessions
            from datetime import datetime
            gbs_sessions = get_sample_sessions()
            today = datetime.now()
            def appt(id, student, parent, phone, rank, type, hour, minute):
                return StudentAppointment(
                    id=id, student_name=student, student_id="", parent_name=parent,
                    phone=phone, rank=rank, appointment_type=type,
                    start_time=today.replace(hour=hour, minute=minute, second=0, microsecond=0),
                    end_time=today.replace(hour=hour+1, minute=minute, second=0, microsecond=0),
                    duration_minutes=60, instructor_name="", location="", notes=None,
                )
            appointments = [
                appt("001", "Khai Collins",    "Orlando Collins",  "909-555-0101", "White Belt",  "CREATE (CODING)", 15, 0),
                appt("002", "Levi Otubuah",    "Edmund Otubuah",   "909-555-0102", "White Belt",  "CREATE (CODING)", 15, 0),
                appt("003", "Lucia Zamarripa", "Karla Zamarripa",  "909-555-0103", "Yellow Belt", "CREATE (CODING)", 15, 0),
                appt("004", "Musa Khan",       "Rabab Khan",       "909-555-0104", "ScratchJR",   "SCRATCH PLUS",    15, 0),
                appt("005", "Jacob Niu",       "Meng Niu",         "909-555-0105", "ScratchJR",   "SCRATCH PLUS",    15, 0),
                appt("006", "Aiden Park",      "Ji-Yeon Park",     "909-555-0106", "Orange Belt", "CREATE (CODING)", 16, 0),
                appt("007", "Sofia Rivera",    "Maria Rivera",     "909-555-0107", "Green Belt",  "CREATE (CODING)", 16, 0),
                appt("008", "Noah Williams",   "Lisa Williams",    "909-555-0108", "White Belt",  "JR",              17, 0),
                appt("009", "Zoe Martinez",    "Ana Martinez",     "909-555-0109", "White Belt",  "JR",              17, 0),
                appt("010", "Ethan Brown",     "Karen Brown",      "909-555-0110", "Yellow Belt", "JR",              17, 0),
            ]
        else:
            # Use cached schedule from last chat response (avoids double API calls)
            cached_gbs = getattr(chatbot, "_last_gbs_sessions", None)
            cached_appts = getattr(chatbot, "_last_appointments", None)

            if cached_gbs is not None or cached_appts is not None:
                logger.info("Using cached schedule for Excel export")
                gbs_sessions = cached_gbs or []
                appointments = cached_appts or []
            else:
                from sites.lineleader.auth import get_bearer_token
                from sites.lineleader.schedules import get_todays_sessions, enrich_sessions_with_children
                from sites.mystudio.schedules import get_todays_appointments

                bearer_token = asyncio.run(get_bearer_token())
                gbs_sessions = get_todays_sessions(bearer_token)
                enrich_sessions_with_children(bearer_token, gbs_sessions)
                try:
                    appointments = get_todays_appointments()
                except Exception as e:
                    logger.warning("MyStudio appointments failed for export: %s", e)
                    appointments = []

        if not gbs_sessions and not appointments:
            return jsonify({"error": "No schedule found"}), 400

        filepath = asyncio.run(create_unified_excel_file(gbs_sessions, appointments))

        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        audit.log_event("error", {"error": f"Export failed: {str(e)}"})
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    # Bind to 0.0.0.0 to allow connections from other machines on the network
    app.run(host="0.0.0.0", port=5001, debug=True)
